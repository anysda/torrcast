"""Сценарий выбора и состояние подготовки релиза."""
# ruff: noqa
# mypy: ignore-errors

from __future__ import annotations

from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS, COPY

from torrcast.usecases.log_command import trace

from torrcast.domain.pick_settings import META_BUDGET, PROBE_BUDGET

from torrcast.domain._series import _Series

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.episode import Episode
from torrcast.domain.episode_file import EpisodeFile
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.map_episodes import map_episodes
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.profile import Profile, REFUSE
from torrcast.domain.recode_note import recode_note
from torrcast.domain.recode_settings import RECODE_HEIGHT
from torrcast.domain.release import Release
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torr_file import TorrFile

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

import contextlib
from importlib import import_module
import re
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Generic, TypeVar

from torrcast.ports.legacy_namespace import legacy_namespace

globals().update(
    legacy_namespace(
        torrcast=("TorrcastError",),
        torrcast__console=(
            "Progress",
            "ask_line",
        ),
        torrcast__search=("RawResult",),
        torrcast__state=("State",),
        torrcast__stream=(
            "ContactWait",
            "Media",
            "TorrServer",
            "probe",
            "swarm_pulse",
            "warm_file",
        ),
        torrcast__timing=("mark",),
    )
)


def _nothing_late() -> list[RawResult]:
    """Долива нет: план собран не поиском (тесты, отладочные ручки) - доливать нечего."""
    return []


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
            if args.release_hash:
                info_hash = legacy_namespace(torrcast__release_pin=("info_hash",))["info_hash"]

                number = next(
                    (
                        number
                        for number, release in enumerate(self.ranked, start=1)
                        if info_hash(release) == args.release_hash
                    ),
                    None,
                )
                if number is None:
                    raise NotFoundError(
                        f"показанного релиза {args.release} у «{self.picture.title}» "
                        "в новой выдаче нет"
                    )
                return [number]
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


def _continue(config: Config, key: str, entry: Entry, args: Args, clock: _Clock) -> int | None:
    """Продолжение по сохранённому выбору. ``None`` — состоянием не обойтись,
    дальше идёт обычный путь с поиском и меню.

    Ни сериал, ни фильм вопросов о продолжении не задают: релиз, дорожка, файл и
    позиция уже записаны.

    ``--voice`` поднимает раздачу ещё до показа (:func:`_revoice` читает её дорожки), и
    хозяин у неё — этот вызов, пока показ её не принял. Принимает он её ровно в одном
    случае: юнит поднялся и играет ТОТ ЖЕ магнит (:attr:`_Voiced.handed`) — дальше её
    уберёт сам юнит. Все прочие исходы — сухой прогон, Ctrl-C на вопросе, «серии тут нет»,
    «смотреть сначала? нет», не поднявшийся юнит — оставляли раздачу навсегда, и убирает
    её теперь ``finally``, по её собственному хэшу.
    """
    own = _Voiced()
    try:
        if not entry.serial:  # фильм (в том числе ошибочно записанный сериалом)
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

    def drop(self, config: Config, release: Callable[..., None] | None = None) -> None:
        """Убрать, если так и не пригодилась. Повторный вызов и пустой хэш безвредны.

        Кроме одного случая: ту же раздачу держит живой показ - ``cast --voice`` на
        играющий фильм поднимает её же (``add`` идемпотентен), и снос выдернул бы её
        из-под экрана (:func:`_held_by_show`). Уберёт её хозяин показа сам.

        ``release`` - чем сносить: подделке отбора хватает списка хэшей, в бою это
        поход в TorrServer.
        """
        if self.handed or not self.torrent_hash:
            return
        torrent_hash, self.torrent_hash = self.torrent_hash, ""
        if _held_by_show(torrent_hash):
            return
        with contextlib.suppress(TorrcastError):
            (release or _release_torrents)(config, [torrent_hash])


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
_selection_bench = import_module("torrcast.usecases.select_bench")
from torrcast.usecases.select_bench import _Bench  # noqa: E402

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


Request = TypeVar("Request")
Result = TypeVar("Result")


class Select(Generic[Request, Result]):
    """Вызывает переданную реализацию сценария отбора."""

    def __init__(self, select: Callable[[Request], Result]) -> None:
        self._select = select

    def run(self, request: Request) -> Result:
        """Отбирает результат для запроса."""
        return self._select(request)
