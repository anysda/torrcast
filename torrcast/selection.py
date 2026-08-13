"""Часть CLI; публичный фасад — :mod:`torrcast.cli`."""

from __future__ import annotations

# fmt: off
__all__ = [
    "CAUTIOUS", "COPY", "EXIT_OK",
    "META_BUDGET", "PROBE_BUDGET", "RECODE_HEIGHT",
    "REFUSE", "TYPE_CHECKING", "Callable",
    "Config", "ContactWait", "Entry",
    "Episode", "EpisodeFile", "InfraError",
    "Media", "NotFoundError", "Picture",
    "Profile", "Progress", "RawResult",
    "Release", "ServerDownError", "State",
    "SwarmError", "TorrcastError", "TorrFile",
    "TorrServer", "_Bench", "_Plan",
    "_Prep", "_Series", "_Voiced",
    "_about", "_continue", "_did_not_answer",
    "_nothing_late", "_remembered", "_revoice",
    "_silenced", "_turned_down", "_voiced",
    "_waiting_note", "ask_line", "contextlib",
    "dataclass", "field", "map_episodes",
    "mark", "probe", "re",
    "recode_note", "swarm_pulse", "threading",
    "time", "trace", "warm_file",
]
# fmt: on

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.commands import (
        Args,
        _Clock,
        _held_by_show,
        _release_torrents,
    )
    from torrcast.playback import _launch, _resume
    from torrcast.ranking import (
        _hms,
        is_candidate,
        misses_episode,
        pick_voice,
    )


import contextlib
import re
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

from torrcast import (
    InfraError,
    NotFoundError,
    SwarmError,
    TorrcastError,
    trace,
)
from torrcast.commands import EXIT_OK, META_BUDGET, PROBE_BUDGET
from torrcast.console import Progress, ask_line
from torrcast.parse import (
    Episode,
    EpisodeFile,
    Picture,
    Release,
    map_episodes,
)
from torrcast.profile import CAUTIOUS, COPY, REFUSE, Profile
from torrcast.recode import RECODE_HEIGHT
from torrcast.reinforce import _nothing_late
from torrcast.search import (
    RawResult,
)
from torrcast.state import Config, Entry, State
from torrcast.stream import (
    ContactWait,
    Media,
    ServerDownError,
    TorrFile,
    TorrServer,
    probe,
    recode_note,
    swarm_pulse,
    warm_file,
)
from torrcast.timing import mark


@dataclass(slots=True)
class _Plan:
    """Что покажем по одной картине: пул релизов и, для сериала, нужная серия.

    План строится на **все** картины франшизы ещё до вопроса — иначе прогрев под меню
    невозможен: греть надо то, что человек, скорее всего, выберет.
    """

    picture: Picture
    ranked: list[Release]
    runtime: float
    #: Потолок ОТБРАКОВКИ, Мбит/с: выше него релиз не берём вовсе (см. :func:`_plan_for`).
    warn_mbit: float
    series: _Series | None = None
    #: Порог ПЕРЕКОДИРОВАНИЯ, Мбит/с: выше него куски перекодируются, а релиз годен.
    #: Ноль - перекодирование выключено, и тогда отбраковка и порог это одно число.
    recode_at: float = 0.0
    #: Потолок для тех, кого сплошной перекод не спасает, Мбит/с: выше него релиз годен
    #: только при перекоде ЦЕЛИКОМ и только пока кадр не выше 1080p
    #: (:attr:`torrcast.state.Config.bitrate_hard_mbit`). Ноль - ступени нет.
    hard_mbit: float = 0.0
    #: Ворота отбора открыты: живых именных кандидатов у картины нет (:func:`gate_open`),
    #: и молчаливые имена идут в очередь наравне с именными.
    loose: bool = False
    #: Ворота последней надежды открыты: живого кандидата с нужной серией нет ВООБЩЕ
    #: (:func:`last_hope`), и в очередь пускается названный HEVC — играть его будет
    #: сплошной перекод. Перекодирование выключено — ворота закрыты всегда.
    last_resort: bool = False
    #: HEVC объявлен своим ресивером как играющий копией через наш HLS.
    copy_hevc: bool = False
    #: Другие части той же франшизы, до меню не доехавшие: их нет в списке картин, но в
    #: выдаче они есть и раздачи у них живые. Нужны одной строке отказа (:func:`kin_line`).
    kin: list[Picture] = field(default_factory=list)
    #: Запрос назвал СЕРИЮ (``s1e1``), а не просто имя. Тогда тип сказан вслух, и дефолт
    #: обязан считаться среди сериалов (:func:`asked_kind`), а не среди тёзок-полнометражек.
    asked_series: bool = False
    #: :attr:`runtime` — настоящая длительность из справки, а не прикидка (:func:`_timed`).
    runtime_known: bool = False
    #: Раздачи картины, не доехавшие даже до :attr:`ranked`: нужного сезона в них нет по
    #: их же именам. Нужны счёту отсева (:func:`queue_drops`), чтобы он сходился с пулом.
    off_season: int = 0
    #: Выдача опоздавших индексеров: круг ушёл по кворуму, а эти доехали позже (TC-118).
    #: Зовётся ОДИН раз и только после ответа на меню - :func:`_topup`.
    late: Callable[[], list[RawResult]] = _nothing_late

    def candidates(self, args: Args) -> list[int]:
        """Очередь релизов: прошедшие ворота, в порядке ранжира - **все, сколько есть**.

        Обрезать очередь тут больше нечем: сколько раздач успеет разобрать показ, решают
        не эти строки, а :meth:`_Bench.resolve` — по приговорам (:data:`MAX_TRIES`) и по
        часам (:data:`PICK_BUDGET`). Пока очередь резалась тремя номерами, отбор сдавался
        со словами «годного релиза нет» ровно тогда, когда рядом в ней стояли живые: в
        замере на тысяче запросов перепроверка в один поток оживляла шесть картин из
        восьми, у которых три раздачи подряд промолчали пирами.

        🔴 TC-432. Ворота проходят ВСЕ, включая верх ранжира. До сих пор он вставал в
        очередь безусловно, и мимо ворот проходил ровно он: «Ведьмак 3: Дикая Охота»
        (игра, ``kind=other``, 35.6 ГБ) стояла единственным кандидатом своей картины на
        запрос «ведьмак s2e4», а «Ван Пис - 923» с нулём сидов - на запрос s1e1. Это
        подмена картины, худший вид брака: человек просит серию сериала, а наверх
        очереди встаёт игра. Ворота при этом отсекают правильно (замер TC-377 по тому
        же корпусу: ложных отсевов ноль) - работать оставалось ровно одно место.

        Безусловной остаётся одна очередь - названная человеком (``--release N``): это
        его явное решение, а не подмена, и судить его воротами нечего.

        Огрызков в очереди нет вовсе (:func:`misses_episode`): тратить на них метаданные
        по DHT незачем — раздача уже своим именем сказала «нужной серии тут нет», и это
        5-40 с за заранее известный отказ. Отбраковка не молчаливая: кого выкинули,
        печатает :attr:`skipped`.

        При открытых воротах (:attr:`loose`) в очередь идут и молчаливые имена: у
        картины иначе нет ни одного живого кандидата, а судить молчание всё равно
        может только ffprobe — и он его тут же и судит.

        При открытых воротах последней надежды (:attr:`last_resort`) к ним добавляется
        названный HEVC до 1080p включительно (:func:`hevc_hope`): играть его будет
        сплошной перекод, и берётся он ровно тогда, когда живого кандидата с нужной
        серией нет вообще.

        Очередь может оказаться пустой - и это ответ, а не повод подставить отсеянное:
        отказ с перечнем причин печатает :meth:`_Bench.resolve` (:func:`unfit_line`).
        """
        if args.release is not None:
            if not 1 <= args.release <= len(self.ranked):
                # 🔴 TC-446. Номер относится к ЭТОЙ картине - той, что человек выбрал в
                # меню или назвал флагом --pick, - и отказ её называет. Безымянный счёт
                # читался как счёт всей выдачи, а считался по одной картине из неё.
                raise NotFoundError(
                    f"у «{self.picture.title}» релизов {len(self.ranked)}, "
                    f"номера {args.release} нет"
                )
            return [args.release]
        queue = [
            n
            for n, r in enumerate(self.ranked, start=1)
            if is_candidate(
                r,
                self.runtime,
                self.warn_mbit,
                self.loose,
                self.hard_mbit,
                self.last_resort,
                self.copy_hevc,
            )
            and not misses_episode(r, self.want)
        ]
        return queue + self._dubbed_tail(queue)

    def _dubbed_tail(self, queue: list[int]) -> list[int]:
        """Хвост очереди: русские раздачи, которых ворота отбора не пустили внутрь.

        🔴 TC-195. Ворота (:func:`is_candidate`) судят ИМЯ раздачи, и раздача, чьё имя
        молчит о качестве, кандидатом не становится, пока у картины есть живой ИМЕННОЙ
        кандидат (:attr:`loose`). Ровно на этом вечер владельца и кончился: у «Тачек»
        2006 года очередь состояла из ОДНОГО релиза - названного 1080p H.264 на 66 сид,
        - его рой промолчал, и показ отказал строкой «раздач в выдаче 5, потрогали 1 -
        до остальных отбор не дошёл». А среди четырёх нетронутых лежали две с дубляжом
        (4.4 ГБ на 3 и на 1 сид), которых никто не спрашивал.

        Отказ был честен про то, что потрогали, и бесполезен для человека: картина в
        каталоге есть, русская дорожка у неё есть, а на экране пусто.

        Хвост, а не послабление ворот, - и это главное. Порядок головы очереди не
        меняется ни на знак: дефолт тот же, запасные те же, и на картине, где голова
        играет, хвоста не видно вовсе - до него просто не доходят. Значит и время до
        картинки прежнее. Меняется ровно один случай: голова кончилась, а показывать
        нечего.

        В хвост идёт только то, у чего РУССКАЯ дорожка названа именем
        (:attr:`~torrcast.parse.Release.dubbed`): молчание про качество мы простить
        готовы - его рассудит ffprobe, - а молчание про язык прощать нечему, иначе
        хвост натащил бы англоязычных рипов туда, где человек ждёт перевод. Потолок
        битрейта и образы дисков хвост не двигает: там ресивер встаёт и играть нечего.
        """
        seen = set(queue)
        return [
            n
            for n, r in enumerate(self.ranked, start=1)
            if n not in seen
            and r.dubbed
            and not misses_episode(r, self.want)
            and is_candidate(
                r, self.runtime, self.warn_mbit, True, self.hard_mbit, True, self.copy_hevc
            )
        ]

    @property
    def want(self) -> Episode | None:
        """Нужная серия, если картина — сериал; у фильма серии нет."""
        return self.series.want if self.series else None

    @property
    def skipped(self) -> list[Release]:
        """Раздачи, отбракованные до каста: нужной серии в них нет по их же именам."""
        return [r for r in self.ranked if misses_episode(r, self.want)]


@dataclass(slots=True)
class _Series:
    """Серии выбранной раздачи: файлы → ``sNeM``, нужный файл и кэш для состояния.

    Пак это или один сезон — решают ФАЙЛЫ, а не имя раздачи: сколько сезонов нашлось в
    путях, столько и будет в списке, и прыжок `s2e5` внутри пака обойдётся без поиска.
    """

    want: Episode
    files: list[EpisodeFile] = field(default_factory=list)

    def choose(self, release: Release, files: list[TorrFile]) -> TorrFile:
        """Файл нужной серии; такой серии в раздаче нет — честная строка со списком."""
        self.files = map_episodes(files, release.season)
        found = next((f for f in self.files if f.at == self.want), None)
        if found is None:
            raise NotFoundError(self._miss_reason(release))
        return next(f for f in files if f.index == found.index)

    def _miss_reason(self, release: Release) -> str:
        """Текст отказа: серии правда нет — или раздача считает в ДРУГОЙ системе.

        🔴 TC-182. У одного сериала сосуществуют ДВЕ нумерации: у «Гинтамы» 38 раздач
        подписаны сезонами S05-S10 (нумерация стриминга), а куски RuTor — сквозным
        счётом через весь сериал (``[01-201]``, ``[202-252]``, ``[253-265]``). Это
        РАЗНЫЕ номера: s5e1 по-стриминговому живёт где-то внутри сквозного 202-252, а
        вычислить, где именно, нельзя честно — границ сезонов не назвало ни одно имя,
        и любой пересчёт был бы выдумкой.

        Признак системы — настоящий и лежит в имени раздачи: сезон она либо назвала
        (:attr:`~torrcast.parse.Release.season` / :attr:`~torrcast.parse.Release.seasons`),
        либо перечислила серии, не назвав сезона, — тот же признак, по которому
        сквозную линейку отличает :func:`torrcast.parse._run_span`. Раздача со сквозным
        счётом на просьбу о пятом сезоне не должна отвечать «серии нет»: серия там,
        скорее всего, ЕСТЬ — под сквозным номером, — и прежний ответ был неправдой
        дважды: и про наличие, и про причину. Поэтому здесь называются ОБЕ системы.
        """
        if (
            self.want.season > 1
            and release.episodes
            and release.season is None
            and not release.seasons
        ):
            span = f"{release.episodes[0]}-{release.episodes[-1]}"
            return (
                f"нумерации разные: {self.want} - это счёт по сезонам, а раздача считает "
                f"серии насквозь через весь сериал ({span}), не называя сезонов "
                f"({self.summary()}) - нужна раздача, подписанная сезоном: "
                "cast <запрос> --release N"
            )
        return (
            f"серии {self.want} в этой раздаче нет ({self.summary()}) - "
            "возьми другую раздачу: cast <запрос> --release N"
        )

    @property
    def table(self) -> list[list[int]]:
        """Список серий для состояния: по нему идут автопереход и прыжки."""
        return [[f.season, f.episode, f.index] for f in self.files]

    def summary(self) -> str:
        """«серий 10: s1e1…s1e10», для пака — ещё и диапазон сезонов."""
        if not self.files:
            return "серий не нашлось"
        seasons = {f.season for f in self.files}
        span = f"сезоны {min(seasons)}-{max(seasons)} · " if len(seasons) > 1 else ""
        return f"{span}серий {len(self.files)}: {self.files[0].at}...{self.files[-1].at}"


def _continue(config: Config, key: str, entry: Entry, args: Args, clock: _Clock) -> int | None:
    """Продолжение по сохранённому выбору. ``None`` — состоянием не обойтись,
    дальше идёт обычный путь с поиском и меню.

    Сериал вопросов не задаёт вовсе: релиз, дорожка и список серий уже выбраны, а
    какую серию и с какого места играть — записано. Фильм спрашивает ровно одно.

    ``--voice`` поднимает раздачу ещё до показа (:func:`_revoice` читает её дорожки), и
    хозяин у неё — этот вызов, пока показ её не принял. Принимает он её ровно в одном
    случае: юнит поднялся и играет ТОТ ЖЕ магнит (:attr:`_Voiced.handed`) — дальше её
    уберёт сам юнит. Все прочие исходы — сухой прогон, Ctrl-C на вопросе, «серии тут нет»,
    «смотреть сначала? нет», не поднявшийся юнит — оставляли раздачу навсегда, и убирает
    её теперь ``finally``, по её собственному хэшу.
    """
    own = _Voiced()
    try:
        if not entry.serial:  # фильм (в том числе ошибочно записанный сериалом) - вопрос один
            if not entry.resumable:
                return None  # продолжать нечего - озвучку выберет обычный путь, по дорожкам
            entry = _voiced(config, entry, args, own)
            code = _resume(config, key, entry, clock=clock, dry=args.dry)
            own.handed = not args.dry  # показ пошёл и раздача та же - дальше она его
            return code
        entry = _voiced(config, entry, args, own)
        if args.episode is not None:  # `cast киберпанк s2e5` - прыжок по кэшу раздачи
            jumped = entry.jump(args.episode.season, args.episode.episode)
            if jumped is None:
                return None  # серии в этой раздаче нет - честно идём искать релиз сезона
            code = _launch(config, key, jumped, _about(jumped), clock, args.dry)
            own.handed = not args.dry
            return code
        if entry.done:  # конец раздачи: сама собой следующая серия не появится
            print(f"«{entry.title}» - {entry.label} была последней в раздаче")
            if ask_line("Смотреть сначала? [Да/нет]")[:1] in {"н", "n"}:
                return EXIT_OK
            first = entry.episodes[0]
            entry = entry.jump(first[0], first[1]) or entry
        code = _launch(config, key, entry, _about(entry), clock, args.dry)
        own.handed = not args.dry
        return code
    finally:
        own.drop(config)


def _remembered(state: State, key: str, found: tuple[str, Entry] | None) -> str:
    """Озвучка, которую пользователь выбирал для этой картины.

    Смотрим по каноническому ключу картины — под ним показ и пишет запись. Запись,
    найденную по тексту запроса (:meth:`State.find`), берём запасным вариантом: у
    одной картины в состоянии могут лежать записи разных запросов («moana» и «моана»),
    и память озвучки не должна зависеть от того, как её позвали в прошлый раз.
    """
    entry = state.get(key) or (found[1] if found is not None else None)
    return entry.voice if entry is not None else ""


@dataclass(slots=True)
class _Voiced:
    """Раздача, поднятая ради ``--voice``: у неё есть хозяин, пока её не принял показ.

    Дорожки читаются из потока, а поток начинается с раздачи в TorrServer — и раздача
    эта переживает наш процесс: живёт она в чужой памяти до перезапуска службы. Пока
    хозяина у неё не было, каждый вызов с ``--voice`` оставлял по раздаче навсегда, в том
    числе ``--dry``, который заведён ровно затем, чтобы следов не оставлять.

    Хозяин один и меняется один раз: если показ поднялся на том же магните, раздача
    достаётся юниту (:attr:`handed`), и убирает её он (:func:`_cmd_worker`). Во всех
    остальных исходах её убирает :meth:`drop` — по СВОЕМУ хэшу, чужого не касаясь.
    """

    torrent_hash: str = ""
    #: Показ принял эту раздачу: юнит играет тот же магнит и уберёт её за собой сам.
    handed: bool = False

    def drop(self, config: Config) -> None:
        """Убрать, если так и не пригодилась. Повторный вызов и пустой хэш безвредны.

        Кроме одного случая: ту же раздачу держит живой показ - ``cast --voice`` на
        играющий фильм поднимает её же (``add`` идемпотентен), и снос выдернул бы её
        из-под экрана (:func:`_held_by_show`). Уберёт её хозяин показа сам.
        """
        if self.handed or not self.torrent_hash:
            return
        torrent_hash, self.torrent_hash = self.torrent_hash, ""
        if _held_by_show(torrent_hash):
            return
        with contextlib.suppress(TorrcastError):
            _release_torrents(config, [torrent_hash])


def _voiced(config: Config, entry: Entry, args: Args, own: _Voiced | None = None) -> Entry:
    """Запись с учётом ``--voice``; без флага — она же, не тронутая и без похода в рой.

    Флага нет — не читаем ничего: этот путь тем и хорош, что обходится состоянием.
    ⚠️ Звать только тогда, когда запись действительно пойдёт в показ. Живая грабля:
    вызов до проверки «есть ли что продолжать» лез в TorrServer за раздачей,
    которую никто играть не собирался, и падал на её магните.

    ``own`` — хозяин поднятой раздачи (:class:`_Voiced`): в списке службы лежат и чужие,
    своей её там ничто не называет, и убрать её можно только по хэшу, который знает он.
    Хозяина не назвали — раздача убирается тут же, на выходе: бесхозной она не остаётся
    ни в одном случае.
    """
    if args.voice is None:
        return entry
    if own is not None:
        return _revoice(config, entry, args, own)
    orphan = _Voiced()
    try:
        return _revoice(config, entry, args, orphan)
    finally:
        orphan.drop(config)


def _revoice(config: Config, entry: Entry, args: Args, own: _Voiced) -> Entry:
    """``--voice`` поверх сохранённого выбора: перечитать дорожки раздачи и взять нужную.

    Нужно ровно для сериала и продолжения: там показ идёт по записи состояния и потока
    никто не читает — ни номеров дорожек, ни подписей взять неоткуда. Платим за это
    метаданными раздачи и одним ffprobe (секунды, с живым прогрессом), и платим только
    когда флаг назван: счастливый путь этой цены не видит.

    Состояние отсюда не пишется: выбор уезжает в запись показа (:func:`_launch`) вместе
    с позицией и серией. Так у ``--dry`` не остаётся следов, а память не переписывается
    показом, который не начался.

    ⚠️ Следов не остаётся и в TorrServer: поднятая здесь раздача записывается хозяину
    (``own``) сразу же, той же строкой, что и поднимается. Раньше её не убирал никто -
    ни при сухом прогоне, ни когда показ до старта так и не доходил.
    """
    torrserver = TorrServer(config.torrserver_url)
    with Progress() as progress:
        progress.phase("дорожки")
        own.torrent_hash = torrent_hash = torrserver.add(entry.magnet)
        torrserver.wait_files(torrent_hash, timeout=META_BUDGET)
        media = probe(torrserver.stream_url(torrent_hash, entry.file_idx), timeout=PROBE_BUDGET)
        progress.phase("")
    entry.audio, entry.voice = pick_voice(media, args, entry.voice)
    return entry


def _about(entry: Entry) -> str:
    """Строка показа по записи состояния: «Киберпанк» · s1e2 · дорожка 1 · с 0:03:20."""
    voice = entry.voice or f"дорожка {entry.audio + 1}"
    parts = [f"«{entry.title}»", entry.label, entry.quality, voice]
    if entry.pos > 0:
        parts.append(f"с {_hms(entry.pos)}")
    return " · ".join(filter(None, parts))


@dataclass(slots=True)
class _Prep:
    """Подготовка одного релиза целиком в фоне: раздача, файл, дорожки.

    Это и есть прогрев под меню. Фазы идут своим ходом в отдельном потоке, а показ
    спрашивает только результат — поэтому 17 секунд ffprobe на «Моане 2» уходят из
    критического пути в паузу между вопросами.

    Каждая фаза имеет **бюджет**: не уложилась — это не «зависло насмерть» без единого
    слова, а :attr:`error` и следующий релиз в очереди.
    """

    number: int
    release: Release
    torrent_hash: str = ""
    #: Прогрев оказался ненужным: показ ушёл на другую картину или другой релиз. Такая
    #: раздача убирается из TorrServer сразу - иначе два лишних торрента тянули бы кэш
    #: и полосу у самого показа.
    dropped: bool = False
    video: TorrFile | None = None
    files: list[TorrFile] = field(default_factory=list)
    media: Media | None = None
    error: str = ""
    #: Отказ, которым кончилась подготовка (``error`` - его строка для человека).
    #: Нужен именно типом: «умерло собственное звено» опознаётся по классу
    #: исключения, а не по префиксу текста - текст пишется языком зрителя и правится.
    failure: TorrcastError | None = None
    #: Спрашивать рой по ПОЛНЫМ бюджетам фазы, без отсрочек на первый контакт
    #: (:data:`PEER_GRACE`, :data:`SWARM_GRACE`). Отсрочки существуют, чтобы не занимать
    #: место в очереди безнадёжной раздачей, и стоит их ошибка ровно этого места - пока
    #: в очереди есть кого спросить. Когда спрашивать больше некого, платить отсрочкам
    #: нечем: терпеливо спрашивается один-единственный релиз (:meth:`_Bench._recheck`).
    patient: bool = False
    contact_wait: ContactWait | None = None
    phase: str = "очередь"
    started: float = field(default_factory=time.monotonic)
    meta: float = 0.0
    read: float = 0.0
    ready: threading.Event = field(default_factory=threading.Event)

    @property
    def want(self) -> TorrFile:
        if self.video is None:
            raise InfraError("файл раздачи не выбран")
        return self.video

    @property
    def found(self) -> Media:
        if self.media is None:
            raise InfraError("поток не прочитан")
        return self.media

    @property
    def timing(self) -> str:
        return f"метаданные {self.meta:.1f} с, дорожки {self.read:.1f} с"


def _turned_down(judged: dict[int, str], number: int, why: str) -> None:
    """Релиз отвергнут: приговор запомнить и положить в след - ровно один раз на решение.

    🔴 TC-194. Единственное место, где рождается запись ``select/drop``, и заведено оно
    затем, чтобы отказ не мог напечататься мимо следа. Так и было: очередь отбора
    (:meth:`_Bench.resolve`) писала запись, а проверка честности (:meth:`_Bench._honest`)
    печатала свои отказы молча - «Наруто» кончился одной строкой на экране и нулём
    событий в недельной ленте, то есть след говорил, что отбор прошёл без единой осечки.

    ``judged`` - те же приговоры по номерам, которыми потом объясняется снижение ступени
    (:func:`stepdown_note`): релиз, которого мы коснулись, обязан числиться отбракованным,
    а не «не дошли».
    """
    judged[number] = why
    trace.emit("select", "drop", release=number, why=why)


def _did_not_answer(number: int, why: str) -> None:
    """Записать осечку роя, не превращая наше ожидание в приговор раздаче."""
    trace.emit("select", "drop", release=number, why=why)


def _waiting_note(prep: _Prep, why: str) -> str:
    """Назвать окончившееся терпение, а не объявлять неизвестный рой пустым."""
    if not _silenced(prep):
        return why
    matched = re.search(r"за (\d+) с", why)
    return f"не дождались за {matched.group(1)} с" if matched else "не дождались"


def _silenced(prep: _Prep | None) -> bool:
    """Осечка ли это РОЯ: про сам релиз мы так ничего и не узнали.

    Отличается тем же, чем отличаются две осечки отбора (:meth:`_Bench.resolve`): ffprobe
    паспорт прочитал - про релиз известно всё, и второй раз спрашивать нечего; рой
    промолчал - неизвестно ничего, кроме того, что раздача не отозвалась. Опознаётся
    ТИПОМ отказа, а не текстом: текст пишется языком зрителя и правится (TC-281).

    «Нужной серии в раздаче нет» и «отдельного видеофайла нет» - это
    :class:`~torrcast.NotFoundError`: про раздачу узнали всё, что хотели, и терпение ей
    ничего не добавит. Молчание роя приезжает :class:`~torrcast.SwarmError`, а не
    уложившаяся в бюджет фаза - вовсе без отказа, одной строкой :attr:`_Prep.error`.
    """
    if prep is None or prep.media is not None:
        return False
    return prep.failure is None or isinstance(prep.failure, SwarmError)


# Оркестратор параллельных прогревов отделён от построения плана и его состояния.
# Старое место импорта сохраняет полный namespace и тестовые подмены.
from torrcast import selection_bench as _selection_bench  # noqa: E402
from torrcast.selection_bench import _Bench  # noqa: E402

_selection_namespace = {
    name: value for name, value in globals().items() if not name.startswith("__")
}
vars(_selection_bench).update(_selection_namespace)
globals().update(
    (name, value) for name, value in vars(_selection_bench).items() if not name.startswith("__")
)


class _SelectionModule(ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if not name.startswith("__") and name in vars(_selection_bench):
            setattr(_selection_bench, name, value)


sys.modules[__name__].__class__ = _SelectionModule
