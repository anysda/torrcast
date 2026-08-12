"""Часть CLI; публичный фасад — :mod:`torrcast.cli`."""

from __future__ import annotations

# fmt: off
__all__ = [
    "CAUTIOUS", "CLOCK", "EXIT_OK",
    "REVIVE_DROP", "REVIVE_LIMIT", "REVIVE_LIVED",
    "REVIVE_PAUSE", "REVIVE_TRIES", "START_BUDGET",
    "TYPE_CHECKING", "VIDEO_EXT", "WATCHED_RATIO",
    "Any", "Callable", "ChromecastReceiver",
    "Clock", "Config", "Encode",
    "Entry", "Feed", "Grid",
    "HlsServer", "InfraError", "NoReturn",
    "NotFoundError", "Path", "Profile",
    "Progress", "Receiver", "Recoder",
    "Release", "State", "Supply",
    "TorrcastError", "TorrFile", "TorrServer",
    "Vault", "Warmer", "_Resume",
    "_Revival", "_asked", "_await_playing",
    "_blame_the_end", "_blamed", "_default_file",
    "_encode_all", "_file_picker", "_handover",
    "_hold", "_launch", "_layout",
    "_next_warmer", "_play", "_recoder",
    "_refuse_hopeless", "_resume", "_warmer",
    "ask_line", "codec_name", "contextlib",
    "dataclass", "detect_profile", "forget_playing",
    "hls_base", "make_receiver", "mark",
    "mark_playing", "os", "pick_video_file",
    "playing_flag", "probe", "recode_note",
    "recodes_whole", "start_play_unit", "stop_play_unit",
    "threading", "time", "trace",
    "unit_active", "unit_why", "warm_file",
    "warm_key", "warm_root", "whole_encode",
    "why",
]
# fmt: on

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.choice import _ctl, _Revivable
    from torrcast.commands import (
        PAUSE_LIMIT,
        PAUSE_SECONDS,
        SAY_SECONDS,
        SOURCE_PAUSE,
        SOURCE_TRIES,
        TRACE_ENV,
        WORKER_DUR,
        Args,
        Watch,
        _Clock,
        _following,
        _held_by_show,
    )
    from torrcast.ranking import _hms
    from torrcast.selection import _about, _Plan


import contextlib
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from torrcast import (
    InfraError,
    NotFoundError,
    TorrcastError,
    trace,
    why,
)
from torrcast.cast import ChromecastReceiver, Receiver, make_receiver
from torrcast.commands import (
    EXIT_OK,
    REVIVE_DROP,
    REVIVE_LIMIT,
    REVIVE_LIVED,
    REVIVE_PAUSE,
    REVIVE_TRIES,
    START_BUDGET,
)
from torrcast.console import Progress, ask_line
from torrcast.parse import (
    VIDEO_EXT,
    Release,
)
from torrcast.profile import CAUTIOUS, Profile
from torrcast.profile import detect as detect_profile
from torrcast.recode import Encode, Recoder, whole_encode
from torrcast.state import WATCHED_RATIO, Config, Entry, State
from torrcast.stream import (
    Feed,
    Grid,
    HlsServer,
    Supply,
    TorrFile,
    TorrServer,
    codec_name,
    forget_playing,
    hls_base,
    mark_playing,
    pick_video_file,
    playing_flag,
    probe,
    recode_note,
    recodes_whole,
    start_play_unit,
    stop_play_unit,
    unit_active,
    unit_why,
    warm_file,
)
from torrcast.timing import CLOCK, Clock, mark
from torrcast.warm import Vault, Warmer, warm_key, warm_root


def _default_file(plan: _Plan, release: Release, files: list[TorrFile]) -> TorrFile:
    """Фильму — самый крупный видеофайл, сериалу — файл нужной серии."""
    return plan.series.choose(release, files) if plan.series else pick_video_file(files)


def _file_picker(args: Args) -> Callable[[_Plan, Release, list[TorrFile]], TorrFile]:
    """``--file N`` — отладочная ручка: взять N-й видеофайл раздачи."""
    if args.file is None:
        return _default_file

    def chosen(plan: _Plan, release: Release, files: list[TorrFile]) -> TorrFile:
        ordered = sorted(files, key=lambda f: f.index)
        videos = [f for f in ordered if f.name.lower().endswith(VIDEO_EXT)]
        if not 1 <= (args.file or 0) <= len(videos):
            raise NotFoundError(f"видеофайлов в раздаче {len(videos)}, номера {args.file} нет")
        return videos[(args.file or 1) - 1]

    return chosen


@dataclass(slots=True)
class _Resume:
    """Прогрев под вопросом «Продолжить?» — то же, что прогрев под меню, но для позиции.

    Продолжение с середины упирается не в поиск (его тут нет вовсе), а в рой: показу
    нужны заголовок файла и то место, где лежит сохранённая позиция, а холодная раздача
    отдаёт новое место секундами. Единственная свободная секунда на этом пути — та, пока
    человек читает вопрос, и она тут и тратится.

    Смещение позиции в байтах берётся из карты опорных кадров
    (:meth:`torrcast.stream.FilmKeys.byte_at`) — той же самой, по которой строится сетка.
    Пропорция «доля фильма от размера файла» сюда не годится: битрейт по фильму гуляет
    вдвое, и промах в проценте — это десятки мегабайт, то есть прогрев не того места.
    """

    torrserver: TorrServer
    entry: Entry
    source: str = ""
    cancelled: bool = False
    #: Хэш поднятой раздачи. Нужен ровно затем, чтобы её было чем убрать: в списке
    #: TorrServer лежат и ЧУЖИЕ раздачи, а «снести всё из list» снесло бы их вместе со
    #: своими; сверх того после перезапуска службы своих в списке не остаётся вовсе
    #: (``save_to_db: false``) - и тогда убрать их нечем, кроме сохранённого хэша
    #: (:meth:`_Bench.drop_all` убирает своё по тем же явным хэшам).
    torrent_hash: str = ""
    #: Показа не будет: поднятое надо убрать, даже если подъём ещё в пути.
    discarded: bool = False

    def start(self) -> None:
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        with contextlib.suppress(TorrcastError):
            self.torrent_hash = torrent_hash = self.torrserver.add(self.entry.magnet)
            if self.discarded:  # отказались, пока раздача поднималась - убираем её сами
                if not _held_by_show(torrent_hash):  # ...но не из-под живого показа
                    self.torrserver.drop(torrent_hash)
                return
            files = self.torrserver.wait_files(torrent_hash)
            self.source = self.torrserver.stream_url(torrent_hash, self.entry.file_idx)
            # Имя файла - подсказка о контейнере для грелки головы: карта, снятая прошлой
            # версией, лежит в кэше без него (:func:`torrcast.stream.container_of`).
            name = next((f.name for f in files if f.index == self.entry.file_idx), "")
            warm_file(self.source, at=self.entry.pos, alive=lambda: not self.cancelled, name=name)

    def enough(self) -> None:
        """Ответ получен — прогрев прекращается, дальше те же байты читает сам показ.

        ⚠️ Это не мелочь и не гигиена, а замер. Прогрев, доигрывающий после Enter'а, —
        это **второй** читатель того же места через TorrServer, и он отбирает у показа
        ровно то, ради чего затевался: в замере пробный прогон вырос с 0.56
        до 1.92 с, а готовность LOAD — с 3.5 до 4.8 с. Смысл прогрева весь в секундах
        ДО ответа; после ответа лучший потребитель полосы — ffmpeg.

        «Сначала» отменяет прогрев по той же причине, только резче: середина фильма
        больше не нужна вовсе.
        """
        self.cancelled = True

    def discard(self) -> None:
        """Показа не будет вовсе — поднятую раздачу убрать по ЕЁ хэшу.

        Ровно два таких выхода: Ctrl-C на вопросе и ``--dry`` (он и заведён затем, чтобы
        ничего не начиналось и следов не оставалось). Раздача при этом уже поднята, а
        живёт она не в нашем процессе: наш умрёт, а она останется качать метаданные в
        чужой RAM до перезапуска TorrServer — та же беда, что у прогрева под меню
        (:meth:`_Bench.drop_all`).

        ⚠️ Ответ «сначала» сюда не относится: раздача та же самая, меняется только место,
        с которого играем, — убрать её значило бы сломать показ.

        И ту же раздачу, что держит параллельный живой показ (та же выдача, тот же
        infohash), тоже не трогаем: снос выдернул бы источник из-под экрана
        (:func:`_held_by_show`). Гонку с ещё не завершённым ``add`` ловит :meth:`_work`.
        """
        self.cancelled = True
        self.discarded = True
        if self.torrent_hash and not _held_by_show(self.torrent_hash):
            self.torrserver.drop(self.torrent_hash)


def _resume(config: Config, key: str, entry: Entry, clock: _Clock, dry: bool = False) -> int:
    """Возобновление: один вопрос и сразу показ. Релиз, файл и дорожка берутся из
    состояния — ни поиска, ни меню, поэтому старт укладывается в 5–15 с.

    Пока задаётся вопрос, раздача уже поднята в TorrServer, а рой прогрет по месту
    сохранённой позиции (:class:`_Resume`): к Enter'у критический путь чаще всего пуст.
    """
    warm = _Resume(TorrServer(config.torrserver_url), entry)
    warm.start()
    question = f"«{entry.title}» остановились на {_hms(entry.pos)}. Продолжить? [Да/сначала]"
    try:
        answer = ask_line(question)
    except BaseException:  # Ctrl-C на вопросе - показа не будет, а раздача уже поднята
        warm.discard()
        raise
    warm.enough()
    mark("рой прогрет")  # TC-108: замер
    if answer[:1] in {"с", "s", "н", "n"}:  # «сначала» / «с начала» / «нет»
        entry.pos = 0.0
    if dry:  # показа не будет: своё поднятое убираем сами, чужого не трогаем
        warm.discard()
    mark("ответы")  # ноль секундомера: Enter после последнего вопроса
    return _launch(config, key, entry, _about(entry), clock, dry)


def _launch(
    config: Config, key: str, entry: Entry, about: str, clock: _Clock, dry: bool = False
) -> int:
    """Показ уезжает в transient-юнит: ``cast`` завершился — показ продолжается."""
    if dry:
        print(f"(--dry) {about} - каста нет")
        return EXIT_OK
    _refuse_hopeless(config, entry)
    # Сначала гасим прошлый показ и только потом пишем свою запись: умирающий юнит по
    # SIGTERM дописывает СВОЮ позицию, и записанный раньше прыжок на s1e5 он бы затёр.
    stop_play_unit()
    state = State.load()
    # Темнота прошлого показа новому не наследуется. Снимает отметку тот же сторож, что
    # её ставит (:attr:`torrcast.state.Entry.dark`), но у убитого по SIGKILL юнита сторожа
    # не было вовсе, а у нового она снимается только с первого опроса приёмника - и до
    # него `cast status` звал бы погасшим показ, который прямо сейчас поднимается.
    entry.dark, entry.dark_why = 0.0, ""
    state.put(key, entry)
    state.save()
    forget_playing(Path(config.hls_dir))  # флажок прошлого показа нам не доказательство
    start_play_unit(key)
    mark("юнит")
    with Progress() as progress:
        _await_playing(config, progress)
    print(f"играю {about} - на ТВ   (старт {clock.total:.0f} с)")
    return EXIT_OK


def _refuse_hopeless(config: Config, entry: Entry) -> None:
    """Отказать ДО юнита, если этой записи на этом приёмнике картинки не видать.

    🔴 Случай ровно один, и он живой (TC-157): кадр 4К приёмник не берёт вовсе - ни в
    чужом кодеке, ни в своём. Замер 09-08-2026 на Q70D: пять заходов LOAD, каждый —
    ``IDLE/ERROR`` сразу после первого сегмента, картинки нет ни разу
    (:attr:`torrcast.profile.Profile.recode_frame`).

    ⚠️ TC-222 сузил проверку до одного условия, и это не ослабление. Ужать кадр вниз
    умеет сплошной перекод - значит отказывать надо не «большому кадру», а большому кадру
    БЕЗ перекода: ``recode: false`` в настройках. С включённым перекодированием ровно та
    же запись теперь играется - 2160p уезжает на приёмник как 1080p.

    Отбор такие релизы отбраковывает сам (:meth:`_Bench._trouble`), но мимо отбора ведут
    две двери: ``--release N`` / ``--file N`` (там человек выбрал сам, и подмен не бывает)
    и продолжение записи, попавшей в состояние через них же. Без этой проверки обе
    кончались одинаково: 86 с «жду телевизор», код 2 и ни слова о причине. Теперь
    причина печатается за доли секунды, а ffmpeg и раздача не поднимаются вовсе.

    Молчим там, где не знаем: кадр ноль — это записи прежних версий, они играются
    как раньше.
    """
    profile = detect_profile(config).profile
    if not entry.frame or entry.frame <= profile.recode_frame:
        return
    if config.recode:
        return
    raise NotFoundError(
        f"{entry.quality or f'{entry.frame}p'} - такой кадр приёмник берёт только ужатым, "
        f"а перекодирование выключено: нужен релиз {profile.recode_frame}p или ниже"
    )


def _await_playing(config: Config, progress: Progress, timeout: float = START_BUDGET) -> None:
    """Дождаться **картинки на экране**, а не «упаковка пошла».

    Две разные вещи, которые легко счесть одной: первый сегмент в tmpfs — это упаковка, а
    картинка — это приёмник, ответивший ``PLAYING``. Спросить приёмник отсюда нельзя:
    сендер к нему должен быть ровно один, и он живёт в юните (см. :mod:`torrcast.cast`).
    Поэтому юнит кладёт флажок (:func:`mark_playing`), а CLI его ждёт — и печатает
    «старт NN с» ровно в тот момент, когда на экране появилось изображение.
    """
    out = Path(config.hls_dir)
    flag = playing_flag(out)
    deadline = time.monotonic() + timeout
    packed = False
    while time.monotonic() < deadline:
        if flag.exists():
            mark("картинка")
            progress.phase("")
            return
        if not packed:
            with contextlib.suppress(OSError):
                packed = any(out.glob("v*.ts"))
            if packed:
                mark("первый сегмент")
        progress.phase("жду телевизор" if packed else "упаковка")
        if not unit_active():
            progress.phase("")
            raise InfraError(f"показ не запустился: {unit_why()}")
        time.sleep(0.2)
    progress.phase("")
    stop_play_unit()
    raise InfraError(f"показ не начался за {timeout:.0f} с - {unit_why()}")


def _recoder(
    source: str,
    audio: int,
    grid: Grid,
    spare: Path,
    config: Config,
    video_mbit: float = 0.0,
    profile: Profile = CAUTIOUS,
) -> Recoder | None:
    """Кодировщик тяжёлых кусков или ``None``, если он не нужен и не может помочь.

    Профиль тяжести считается из уже снятой карты опорных кадров: байты и секунды каждого
    сегмента известны до упаковки, и это ноль запросов к рою. Отказ бывает честный —
    выключено настройкой, сетка не по кадрам (тогда границы не совпадут с картой), карта
    снята прошлой версией и смещений не несёт, — и о нём говорится вслух.
    """
    from torrcast.recode import Encode, Recoder, Weights
    from torrcast.stream import AUDIO_MBIT, TS_OVERHEAD, film_keys

    if not config.recode:
        return None
    if not grid.on_keys:
        print("сетка не по опорным кадрам - тяжёлые куски перекодировать не берусь", flush=True)
        return None
    try:
        keys = film_keys(source)
    except InfraError as exc:
        print(f"профиль тяжести не снят ({why(exc)}) - играю как есть", flush=True)
        return None
    # Сколько уедет на ТВ: видеодорожка идёт копией, звук всегда AAC, сверху оверхед
    # mpegts. Паспорт молчит (mp4 без тегов) - поправка наберётся по факту, как раньше.
    delivered = (video_mbit + AUDIO_MBIT) * TS_OVERHEAD if video_mbit > 0 else 0.0
    weights = Weights.of(keys, grid, delivered=delivered)
    if weights is None:
        print("карта без смещений - профиль тяжести не построить, играю как есть", flush=True)
        return None
    print(
        f"профиль тяжести: контейнер {weights.container:.1f} Мбит/с, "
        + (
            f"на ТВ уедет {delivered:.1f} (видео {video_mbit:.1f} по паспорту)"
            if delivered > 0
            else "веса видеодорожки в паспорте нет - поправку наберу по факту"
        ),
        flush=True,
    )
    return Recoder(
        source=source,
        audio=audio,
        grid=grid,
        spare=spare,
        weights=weights,
        threshold=config.recode_at_mbit,
        # Потолок веса куска - тот же, которым меряет показ: у каждого приёмника свой
        # (:attr:`torrcast.profile.Profile.max_segment_bytes`).
        cap=profile.max_segment_bytes,
        encode=Encode(preset=config.recode_preset, mbit=config.recode_mbit),
        ahead=config.recode_ahead,
        cache_mb=config.recode_cache_mb,
        head_wait=config.recode_head_wait,
        log=lambda text: print(text, flush=True),
    )


def _encode_all(
    config: Config,
    codec: str,
    video_mbit: float = 0.0,
    depth: int = 0,
    profile: Profile = CAUTIOUS,
    frame: int = 0,
    hdr: bool = False,
) -> Encode | None:
    """Чем перекодировать ВЕСЬ файл или ``None`` — если видео уезжает копией, как всегда.

    Решение файл-уровневое и принимается один раз, по паспорту ffprobe: приёмник либо
    декодирует поток, либо нет (:func:`torrcast.stream.recodes_whole`), и середины тут не
    бывает. Посегментное решение по весу и битрейту на таком файле давало **смешанный**
    поток H.264 и HEVC — на живом Q70D это 24 с картинки и вечная петля «залип →
    перезагрузка»: ровно на границе первого не перекодированного куска.

    🔴 Вопрос задаётся белым списком: копия достаётся ТОЛЬКО тому, что в нём названо
    (:meth:`torrcast.profile.Profile.verdict`). Пока список был чёрным, VP9 и AV1 уезжали
    в mpegts копией всюду, куда отбор не дотянулся, — на релизе, названном руками
    (``--release N``), и на записи возобновления. Приёмник такой поток не начинает вовсе:
    ``LOAD`` не взят, ``IDLE/ERROR``. Кодек, которого мы не мерили, — честный отказ
    ОТБОРА, но если файл всё же играем, он идёт сплошным перекодом, а не копией.

    ``depth`` - глубина цвета из того же паспорта (:attr:`torrcast.state.Entry.depth`).
    🔴 Спрашивается она наравне с кодеком, потому что имени кодека не хватает: Hi10P
    зовётся тем же ``h264``, а приёмник его не декодирует (:data:`COPY_DEPTH`). Ноль -
    глубину не спрашивали (запись прежней версии), решаем по одному кодеку.

    ``frame`` - ступень кадра из того же паспорта (:attr:`torrcast.stream.Media.frame`).
    🔴 TC-222. Спрашивается она наравне с кодеком и глубиной по той же причине: 2160p
    приёмник не берёт и в посильном кодеке (TC-157), а ужать кадр может только перекод.
    Поэтому кадр выше потолка приёмника - это не отказ, а сплошной перекод со скейлом
    вниз, и потолок едет в :attr:`torrcast.recode.Encode.ceiling` вместе с самим кадром:
    решение «во что ужимать» принимается здесь, один раз, до первого сегмента.

    ``hdr`` - картинка в HDR (:attr:`torrcast.stream.Media.hdr`). Тонемап включается
    только вместе с настройкой (:attr:`torrcast.state.Config.recode_tonemap`), и по
    умолчанию он выключен: замер его цены лежит там же.

    Битрейт — не потолок, а **цель**, и она считается от источника. ``recode_mbit``
    остаётся потолком, но брать его всегда нельзя: 🔴 замер на живом Q70D (TC-29,
    «Bocchi the Rock» — 1.3 Мбит/с HEVC) показал, что перекод «в 9 Мбит/с» раздувает
    лёгкое аниме в семь раз, кладёт в сегменты 18.3 и 21.4 МБ при потолке 16 и тратит
    процессор на биты, которых в источнике нет. Отсюда :data:`FULL_GAIN` — во сколько
    раз H.264 тем же ``ultrafast`` (без CABAC и почти без анализа) дороже HEVC при
    сравнимой картинке, — и :data:`FULL_FLOOR`, ниже которого 1080p разваливается.

    Второй повод для сплошного перекода — не кодек, а вес: выше
    :attr:`torrcast.state.Config.bitrate_hard_mbit` тяжёл КАЖДЫЙ кусок, и посегментный
    кодировщик выродился бы в сотню коротких ffmpeg вместо одного длинного. Живой класс,
    ради которого написано, — аниме-BD-ремуксы 1080p на 28–37 Мбит/с; замер на 4 vCPU:
    ``h264`` 37.8 Мбит/с → 9 Мбит/с идёт 3.4× реального времени, синтетический ``hevc``
    29.9 Мбит/с → 2.35×. Потолок отбора для них — ``bitrate_recode_mbit``.
    """
    if not config.recode:
        return None
    heavy = video_mbit > config.bitrate_hard_mbit
    if not recodes_whole(codec or "", depth, profile, frame) and not heavy:
        return None
    return whole_encode(
        config.recode_mbit,
        video_mbit=video_mbit,
        frame=frame,
        ceiling=profile.recode_frame,
        hdr=hdr and config.recode_tonemap,
    )


def _layout(
    config: Config,
    source: str,
    length: float,
    codec: str,
    video_mbit: float,
    say: Any = None,
    depth: int = 0,
    profile: Profile = CAUTIOUS,
    frame: int = 0,
    hdr: bool = False,
) -> tuple[Grid, Encode | None]:
    """Сетка сегментов и решение «перекодировать файл целиком» - одной парой.

    Отдельной функцией потому, что считать это приходится дважды и обязательно
    одинаково: один раз показу (:func:`_play`), другой - прогреву следующей серии впрок
    (:func:`_next_warmer`). Разойдись они хоть в одном знаке после запятой - прогретое
    легло бы под другим ключом (:func:`torrcast.warm.warm_key`), и показ, ради которого
    всё грелось, своего же прогретого не нашёл бы.

    🔴 Ровно поэтому паспорт сюда приходит целиком - кодек, глубина цвета, кадр и HDR:
    пока глубину знал один прогрев, а показ решал по имени кодека, десятибитный H.264
    уезжал на ТВ копией и вставал намертво (:func:`torrcast.stream.recodes_whole`).

    Порядок внутри тоже не случаен: сплошной перекод решается ДО сетки, потому что от
    битрейта перекода зависит вес каждого куска, а значит и то, где сетка ставит границы.
    🔴 TC-222. На ужатом 4К это перестаёт быть тонкостью и становится условием показа: под
    сплошным перекодом вес куска задаём МЫ, и считать его по карте исходника нельзя. У
    4К-исходника на 21 Мбит/с карта обещает сегменты вдвое легче наших девяти - сетка
    нарезала бы по 20 с, а наши же 9 Мбит/с положили бы в такой кусок 22 МБ при потолке
    приёмника 16 (:attr:`torrcast.profile.Profile.max_segment_bytes`). Поэтому в сетку
    едет ``fixed_mbit`` - наш битрейт, а не исходника.

    🔴 TC-501. Наш битрейт тут - это ``maxrate``, а не цель: см. комментарий у самого
    ``fixed_mbit``. Считать вес куска по средней цели значит обещать себе тем больше,
    чем труднее материал, - и на сплошном перекоде обещание промахивалось на все восемь
    процентов ``MAXRATE_GAIN``, ровно вверх, ровно на длинных кусках.
    """
    from torrcast.stream import AUDIO_MBIT, TS_OVERHEAD, grid_for

    whole = _encode_all(config, codec, video_mbit, depth, profile, frame, hdr)
    grid = grid_for(
        source,
        length,
        config.hls_segment,
        config.hls_keyframes,
        say=say,
        delivered_mbit=(video_mbit + AUDIO_MBIT) * TS_OVERHEAD if video_mbit > 0 else 0.0,
        ceiling_mbit=config.recode_mbit if config.recode else 0.0,
        # Сплошной перекод: вес куска задаём мы сами, карта источника тут не судья.
        # 🔴 TC-501. Задаём его МГНОВЕННЫМ потолком кодера (:attr:`torrcast.recode.Encode.maxrate`),
        # а не целью: цель - это средний битрейт по прогону, а в отдельный кусок кодер
        # вправе положить вплоть до потолка (:data:`torrcast.recode.MAXRATE_GAIN`), и на
        # трудном материале он ровно это и делает. Замер на стенде (1080p10 40 Мбит/с,
        # ultrafast, цель 9): насыщенный кусок уехал на 10.22 Мбит/с при обещанных сеткой
        # 9.47 - промах ровно в ``MAXRATE_GAIN``. Сетка на этом обещании разрешала себе
        # куски до 13.5 с, а такой кусок весит 17 МБ при потолке приёмника 16: он рождался
        # за потолком ещё до всякой выкладки, и ловить его на выходе было уже нечем.
        fixed_mbit=(whole.maxrate + AUDIO_MBIT) * TS_OVERHEAD if whole is not None else 0.0,
        # Потолок веса куска - у каждого приёмника свой (:mod:`torrcast.profile`).
        cap=profile.max_segment_bytes,
    )
    if whole is not None:
        # 🔴 TC-501, вторая половина. Сетка режет ТОЛЬКО по опорным кадрам, и там, где
        # один GOP сам по себе длиннее потолка, резать ей нечем - кусок остаётся длинным
        # («влез - или один GOP тяжелее потолка», :meth:`torrcast.stream.Grid.on_keyframes`).
        # Замер на живом Q70D («Эксперименты Лэйн», BDRip hi10p): честной сетки мало,
        # у неё осталось два куска по 15.2 с, и наши 9 Мбит/с положили в них 17 и 16 МБ
        # при потолке 16 - показ встал на 1:58 ровно на них.
        #
        # Поэтому цель считается ОТ САМОГО ДЛИННОГО куска, который в сетке всё-таки
        # остался, - тем же и единственным местом, где живёт потолок (:meth:`Encode.fit`),
        # и ровно так же, как её считает заход посегментного кодировщика (TC-483). Прогон
        # сплошного перекода один на весь показ и идёт одним ``-b:v``, так что судит его
        # худший кусок: иначе кусок, который резать нечем, не влезет никогда и ничем.
        # Чёткость тут и торгуется: гейт «ноль подгрузов» стоит выше неё.
        #
        # ⚠️ Хвост в судьи не берётся, и это не поблажка. Последний кусок сетки такой,
        # какой остался (:meth:`torrcast.stream.Grid.on_keyframes`), потолок веса на него
        # не распространялся никогда, и длина у него не связана ни с картой, ни с нашим
        # битрейтом. Замер: на 4К-карте с GOP 8.5 с хвост вышел 16.5 с и утянул бы цель
        # всего фильма с 9.0 до 6.12 Мбит/с - то есть один кусок в конце кино торговал бы
        # чёткостью всех остальных.
        judges = max(grid.count - 1, 1)
        whole = whole.fit(max(grid.span(k) for k in range(judges)), profile.max_segment_bytes)
    return grid, whole


def _next_warmer(
    config: Config,
    torrserver: Any,
    torrent_hash: str,
    entry: Entry,
    profile: Profile = CAUTIOUS,
) -> Warmer | None:
    """Прогрев СЛЕДУЮЩЕЙ серии - тем же механизмом, каким грелась текущая.

    Зовётся лениво и ровно один раз: когда текущая серия уже лежит на диске целиком и
    больше не нуждается ни в одном байте раздачи (:meth:`torrcast.warm.Warmer._chain`).
    Раньше этого момента следующая серия не имеет права ни на полосу, ни на процессор.

    ⚠️ Побочный смысл этой сборки не меньше самого прогрева. Автопереход на следующую
    серию (:func:`_cmd_worker`) начинается с двух вопросов к раздаче: паспорт файла
    (:func:`probe` - длительность для порога 95 %) и карта опорных кадров
    (:func:`torrcast.stream.film_keys` - сетка и манифест). Посреди обрыва связи спросить
    их не у кого, и показ, у которого следующая серия ЛЕЖИТ на диске, всё равно уткнулся
    бы в мёртвую раздачу. Здесь оба вопроса задаются заранее и оба ложатся в кэш на диск.

    ``None`` - греть нечего: фильм, последняя серия раздачи или запись без списка серий.
    """
    from torrcast.recode import RECODE_DIR
    from torrcast.stream import hls_dir

    following = entry.advance()
    if following.done or not following.label:
        return None
    source = torrserver.stream_url(torrent_hash, following.file_idx)
    media = probe(source, timeout=WORKER_DUR)
    video_mbit = max(0.0, media.video_bps / 1e6)
    # 🔴 Профиль тот же, что у показа: разойдись они - прогретое ляжет под другим ключом
    # (:func:`torrcast.warm.warm_key`), и показ своего же прогретого не найдёт.
    grid, whole = _layout(
        config,
        source,
        media.duration,
        media.video or "",
        video_mbit,
        depth=media.depth,
        profile=profile,
        frame=media.frame,
        hdr=media.hdr,
    )
    recoder = (
        None
        if whole is not None
        else _recoder(
            source,
            following.audio,
            grid,
            hls_dir(config.hls_dir) / RECODE_DIR,
            config,
            video_mbit=video_mbit,
            profile=profile,
        )
    )
    title = " ".join(filter(None, (following.title, following.label)))
    return _warmer(
        config,
        source,
        following.audio,
        grid,
        0.0,
        title,
        whole=whole,
        recoder=recoder,
        profile=profile,
    )


def _warmer(
    config: Config,
    source: str,
    audio: int,
    grid: Grid,
    start: float,
    title: str,
    whole: Any = None,
    recoder: Any = None,
    follow: Any = None,
    profile: Profile = CAUTIOUS,
) -> Warmer | None:
    """Фоновый прогрев всего фильма на диск или ``None``, если он выключен.

    🔴 **Прогрев кодирует кусок ровно тем же решением, что и живая упаковка.** Куски
    одного показа приходят приёмнику из двух мест — из окна упаковки и с диска
    (:meth:`torrcast.stream.Feed.segment`), — и для приёмника это одна лента. Разойдись
    решение о кодировании, и на стыке двух источников меняется SPS: другой профиль, другая
    энтропийная кодировка, другая глубина буфера кадров — то есть декодер обязан
    переинициализироваться посреди фильма. Поэтому решение здесь ОДНО на обоих:

    * кодек, который приёмник не декодирует, — сплошной перекод (``whole``), и у показа,
      и у прогрева;
    * тяжёлые куски — точечный перекод тем же :class:`Encode`, которым их берёт живой
      кодировщик (``recoder``), и ровно на тех же слотах;
    * всё остальное — копия.

    ⚠️ Прежде тут стояло «есть хоть один тяжёлый кусок — греть весь фильм перекодом».
    Замер на лёгком материале («Тачки 3»: 5 тяжёлых кусков из 525): живая упаковка отдавала
    копию релиза, а прогрев клал на диск сплошной ``ultrafast``, и SPS этих двух не
    совпадали ни одним байтом. Стык был не редкостью, а нормой работы — прогрев обгоняет
    показ и отдаёт ему свои куски.
    """
    if not config.warm:
        return None
    encode = whole
    spots = () if whole is not None or recoder is None else tuple(recoder.targets)
    vault = Vault(
        root=warm_root(config.warm_dir),
        key=warm_key(source, audio, grid, encode, spots),
        budget=int(config.warm_budget_gb * 1e9),
        title=title,
    )
    spot_encode = getattr(recoder, "encode", None) if spots else None
    trace.plan(
        pack="recode" if encode is not None else "copy",
        warm="recode" if encode is not None else "copy",
        spots=len(spots),
        preset=str(getattr(spot_encode or encode, "preset", "")),
        mbit=float(getattr(spot_encode or encode, "mbit", 0.0)),
    )
    return Warmer(
        source=source,
        audio=audio,
        grid=grid,
        vault=vault,
        encode=encode,
        spots=spots,
        spot_encode=spot_encode,
        began_at=grid.slot_at(start),
        # Потолок веса куска - свойство приёмника, и прогреву он нужен ровно затем, чтобы
        # «прогрето NN» называло то, что показ и правда возьмёт с диска
        # (:attr:`torrcast.warm.Warmer.warmed`, :meth:`torrcast.stream.Feed._warm`).
        cap=profile.max_segment_bytes,
        rate=config.warm_rate,
        follow=follow,
        rival=recoder,
        log=lambda text: print(text, flush=True),
    )


def _play(
    config: Config,
    source: str,
    audio: int,
    about: str,
    clock: _Clock,
    watch: Watch | None = None,
    duration: float = 0.0,
    receiver: Receiver | None = None,
    codec: str = "",
    depth: int = 0,
    follow: Any = None,
    supply: Supply | None = None,
    profile: Profile = CAUTIOUS,
    frame: int = 0,
    hdr: bool = False,
    journal: str = "",
) -> int:
    """Упаковка → раздача по http на голом IP → приёмник. Своих демонов нет: и ffmpeg,
    и раздача живут ровно на время показа и гасятся вместе с ним, что бы ни случилось.

    Упаковка за показ перезапускается столько раз, сколько человек перемотал: манифест
    обещает приёмнику весь фильм, а :class:`Feed` пакует то место, которое он попросил.
    Раздача, приёмник и LOAD при этом одни на весь показ.

    ``follow`` - чем прогреву заняться, когда эта серия ляжет на диск целиком
    (:attr:`torrcast.warm.Warmer.follow`); у фильма его нет и быть не может.

    ``supply`` - источник показа (:class:`torrcast.stream.Supply`): служба раздач и наша
    раздача в ней. Спрашивают его только на краю показа, зато прежде, чем объявить показ
    погасшим, - иначе за аварию источника отвечает приёмник, который ни при чём.

    ``profile`` - пороги ПРИЁМНИКА (:mod:`torrcast.profile`): вес куска, терпение, сторож
    нуджей, удержание запроса вместо 404. Умолчание осторожное - тот же Q70D, что и был.
    """
    from torrcast.recode import RECODE_DIR
    from torrcast.stream import hls_dir

    out = hls_dir(config.hls_dir)
    start = watch.entry.pos if watch else 0.0
    length = watch.entry.dur if watch else duration
    tls = config.transport == "https"
    video_mbit = max(0.0, watch.entry.vbps) if watch else 0.0
    journal = journal or f"[сеанс {trace.session_id()}]"
    # Сетка сегментов снимается с самого файла и дальше не меняется: она же в манифесте,
    # она же в команде ffmpeg. Всё, что показ говорит о времени, считается по ней.
    #
    # Сетке нужен не только шаг, но и вес. Сегмент тяжелее ~19 МБ приёмник не
    # доигрывает, а выбрасывает буфер и качает его заново, поэтому граница ставится с
    # оглядкой на предсказанный вес куска - а он зависит и от паспорта (что уедет на ТВ),
    # и от того, перекодируем ли мы тяжёлое (тогда кусок не тяжелее ``recode_mbit``).
    # Кодек, который приёмник не декодирует, - это решение на весь показ, а не на кусок:
    # перекодирует сама упаковка, одним прогоном, и кодировщик тяжёлых кусков не нужен -
    # перекодировать поверх перекода нечего. Решается это ДО сетки: от битрейта перекода
    # зависит вес каждого куска, а значит и то, где сетка поставит границы.
    grid, whole = _layout(
        config,
        source,
        length,
        codec,
        video_mbit,
        say=lambda text: print(text, flush=True),
        depth=depth,
        profile=profile,
        frame=frame,
        hdr=hdr,
    )
    mark("сетка", сегментов=grid.count, покадрам=grid.on_keys)
    if whole is not None:
        # Причина перекода называется вслух: кодек с глубиной - или вес, и тогда с числом.
        # А вместе с ней и ужатый кадр: 2160p наружу уезжает как 1080p (TC-222).
        name = codec_name(codec, depth)
        print(
            recode_note(
                name,
                0.0 if recodes_whole(codec, depth, profile, frame) else video_mbit,
                frame,
                whole.out_frame,
            ),
            flush=True,
        )
        mark(
            "сплошной перекод",
            кодек=name,
            пресет=whole.preset,
            мбит=round(whole.mbit, 2),
            кадр=whole.out_frame,
            тонемап=whole.hdr,
        )
    # Профиль тяжести всего фильма известен со старта - он считается из уже снятой
    # карты опорных кадров и не стоит ни одного запроса к рою. Тяжёлые куски кодировщик
    # начнёт перекодировать сразу, пока играет остальное.
    recoder = (
        None
        if whole is not None
        else _recoder(
            source,
            audio,
            grid,
            out / RECODE_DIR,
            config,
            video_mbit=video_mbit,
            profile=profile,
        )
    )
    # Прогрев поднимается ПОСЛЕ старта показа (ниже), а собирается здесь: ему нужны и
    # сетка, и решение о перекодировании - те же, что у живой упаковки.
    warmer = _warmer(
        config,
        source,
        audio,
        grid,
        start,
        about,
        whole=whole,
        recoder=recoder,
        follow=follow,
        profile=profile,
    )
    feed = Feed(
        source=source,
        audio=audio,
        out=out,
        grid=grid,
        readrate=config.hls_readrate,
        burst=config.hls_burst,
        keep=config.hls_keep,
        # Сколько держать запрос вместо 404 - свойство приёмника: Q70D после 404 молчит
        # минутами, а приставка Android TV берёт следующий LOAD через девять секунд.
        wait=profile.hold_seconds,
        # Потолок веса куска нужен раздаче отдельно от сетки: прогретое на диске уезжает
        # на ТВ мимо упаковки, и взвесить его больше негде (:meth:`Feed._warm`).
        cap=profile.max_segment_bytes,
        log=lambda text: print(text, flush=True),
        recoder=recoder,
        encode=whole,
        vault=None if warmer is None else warmer.vault,
    )
    server = HlsServer(
        out, config.hls_cert, config.hls_key, port=config.hls_port, tls=tls, feed=feed
    )
    # Серт приёмнику нужен только затем, чтобы проверить нашу раздачу: по http проверять
    # нечего, и mock не должен делать вид, что что-то проверил. Готовый приёмник приходит
    # с сериалом: он один на весь юнит (см. :func:`_cmd_worker`).
    if receiver is None:
        receiver = make_receiver(
            config.receiver, config.tv or "", config.hls_cert if tls else "", profile=profile
        )
    # Сетку знает показ, а спотыкается о неё приёмник: и прыжок сторожа, и подъём после
    # отказа обязаны мерить кусками, а не секундами
    # (:meth:`torrcast.cast.ChromecastReceiver._nudge`). Приёмник живёт весь юнит и
    # достаётся следующей серии - сетка у неё своя, и назвать её надо каждой.
    if isinstance(receiver, ChromecastReceiver):
        receiver.next_cut = grid.after
    url = f"{hls_base(config)}/index.m3u8"
    try:
        server.start()
        mark("раздача")
        # Упаковку начинаем сами, не дожидаясь первого запроса: ресиверу нужен готовый
        # кусок сразу, иначе LOAD упирается в ожидание ffmpeg и старт растёт на глазах.
        if recoder is not None:
            recoder.played = start
            recoder.start()
        feed.restart(grid.slot_at(start))
        mark("упаковка пошла")
        receiver.play(url, about, at=start)
        mark("LOAD взят")
        print(f"{journal} играю {about} - на ТВ   (старт {clock.total:.0f} с)", flush=True)
        # ⚠️ Прогрев стартует ровно ЗДЕСЬ и ни строкой выше: путь до картинки он не
        # удлиняет ни на секунду - ни своим ffmpeg, ни чтением каталога. Всё, что он
        # делает, происходит уже при играющем показе и на остатке процессора.
        if warmer is not None:
            warmer.start()
        expected_end = _hold(receiver, feed, watch, warmer, supply, profile, journal=journal)
    finally:
        # Позиция фиксируется при любом исходе, включая SIGTERM, и делается это ПЕРВЫМ
        # делом: показ, доигранный до конца файла, отмечает «досмотрено» ровно здесь, а
        # приёмнику ниже нужно уже готовое состояние - по нему он и узнаёт, конец это
        # показа или стык серий.
        if watch is not None:
            watch.flush()
            trace.emit(
                "session",
                "session_end",
                pos=round(watch.entry.pos, 1),
                dur=round(watch.entry.dur, 1),
                watched=bool(watch.done),
            )
        if warmer is not None:
            warmer.stop()
            # Досмотрено (порог 95 %) - прогретое стирается: держать на диске фильм,
            # который уже посмотрели, незачем. Прерванный показ прогретое сохраняет:
            # `cast` завтра продолжит с диска и без сети.
            if watch is not None and watch.done:
                warmer.vault.clear()
                print("досмотрено - прогретое с диска убрал", flush=True)
        # ⚠️ suppress(Exception), а не TorrcastError: pychromecast на полуживом соединении
        # роняет что угодно, а ffmpeg и раздача обязаны погаснуть в любом случае - иначе
        # процесс уходит, а они остаются.
        with contextlib.suppress(Exception):
            # Показ кончился - приложение приёмника закрываем, чтобы ТВ вернулся в
            # исходное состояние: иконка Default Media Receiver иначе висит до своего
            # таймаута простоя и оттягивает автовыключение.
            # Исключение ровно одно - стык серий: следующая серия грузится в то же
            # приложение, и гасить его между ними значит моргать экраном на каждой.
            receiver.stop(quit_app=not _handover(watch))
        feed.stop()
        server.stop()

    report = getattr(receiver, "report", None)
    if report is None:
        return EXIT_OK
    print(f"{journal} {report.line()}")
    # Серию обрывают намеренно на пороге 95 % - хвост упаковки декодеру и не отдавали.
    if not report.ok and not expected_end and not (watch is not None and watch.done):
        _blame_the_end(supply)
    return EXIT_OK


def _handover(watch: Watch | None) -> bool:
    """Правда ли показ передают следующей серии, а не заканчивают.

    Порог 95 % уже записал в состояние следующую серию (:meth:`Watch.flush`), поэтому
    ответ лежит там же, где его читает :func:`_cmd_worker`, — двух разных мнений о конце
    показа быть не должно.
    """
    return watch is not None and watch.done and _following(watch.key) is not None


def _blame_the_end(supply: Supply | None) -> NoReturn:
    """Показ кончился недосмотренным - назвать виноватого, и назвать верно. Всегда бросает.

    🔴 Последняя строка показа - последняя возможность сказать правду. Досюда доходит и
    показ, который не успел сдвинуться с нуля: поднимать его некому и неоткуда
    (:class:`_Revival` без позиции не работает), - и раньше он кончался обвинением
    «приёмник не досмотрел поток» при живом приёмнике и мёртвой службе раздач. Замерено на
    стенде: перезапуск службы под показом давал ровно эту строку, и про источник в ней не
    было ни слова.

    Спросить источник тут можно спокойно: показ уже кончился, горячего пути нет, а
    человеку и следу уходит одна и та же причина.
    """
    why_source = _blamed(supply)
    if why_source:
        trace.offline(why=why_source, asked=True)
        raise InfraError(f"источник не читается ({why_source}) - показ оборван, цифры выше")
    raise InfraError("приёмник не досмотрел поток - цифры выше")


def _blamed(supply: Supply | None, clock: Clock = CLOCK) -> str:
    """Причина аварии ИСТОЧНИКА для строки человеку; пусто - источник тут ни при чём.

    ⚠️ Отличается от :func:`_asked` двумя вещами, и обе - из замеров на живой службе.

    Первая: служба, которую перезапустили, поднимается за три секунды, и к тому мгновению,
    когда показ признан погасшим, она уже отвечает. Спросить её «сейчас всё хорошо?» мало -
    хорошо стало потому, что мы сами вернули ей раздачу магнитом, а это и есть
    доказательство того, что источник падал. Такую темноту вешать на приёмник нельзя.

    Вторая: спрашивать надо не один раз. Замер (05:37:48.3 - 05:37:51.5): все три секунды
    своей остановки старая служба продолжала отвечать на ``/echo`` и отдавать список
    раздач - «мёртвой» она не выглядит НИ РАЗУ, а показ умирает как раз внутри этого окна.
    Один вопрос в момент смерти застаёт источник здоровым и врёт. Поэтому вопросов
    несколько (:data:`SOURCE_TRIES`) и растянуты они на пару выдержек: показ к этому
    моменту уже кончился, и шесть секунд на правду - куда меньшая цена, чем ложь.
    """
    for left in range(SOURCE_TRIES, 0, -1):
        why_source = _asked(supply)
        if why_source:
            return why_source
        if supply is not None and supply.restored:
            return "TorrServer перезапускался - раздачу вернул магнитом"
        if left > 1 and supply is not None:
            clock.sleep(SOURCE_PAUSE)
    return ""


def _asked(supply: Supply | None) -> str:
    """Спросить ИСТОЧНИК: что с ним не так; пусто - он в порядке (и раздача при трекерах).

    Единственное место, где показ обращается к источнику, и зовут его только с края
    показа: упаковка объявила себя мёртвой либо приёмник погасил экран. В горячем пути
    этих вопросов нет и быть не может - раздача сегментов не ждёт ни журнал, ни лишний
    запрос.

    Возврат раздачи магнитом говорится вслух ровно здесь, одной строкой и одним событием
    следа: два разных мнения о том, что сделано с источником, - это то же самое, что
    молчание.
    """
    if supply is None:
        return ""
    why_source = supply.check()
    if supply.restored:
        trace.resupply(torrent=supply.torrent_hash, ok=True)
        print("источник вернулся - раздачу добавил магнитом заново", flush=True)
    return why_source


@dataclass(slots=True)
class _Revival:
    """Показ погас - ждём факта возврата сети и поднимаем LOAD с сохранённого места.

    🔴 Терпение приёмника меньше нашего и кончается молча. Замер 09-08-2026 на живом
    Samsung Q70D: медиасессия умирает через 23.5 с стоящей картинки, а приложение висит на
    экране ещё 301 с после этого (прежние «примерно четыре минуты» были склейкой этих
    двух сроков и не равны ни одному из них). Куски, пока сессия жива, приёмник
    перезабирает сам - по HTTP, а не повторами LOAD. Строка при этом честная и позиция
    сохранена, но экран чёрный до тех пор, пока человек не сходит к консоли. Продукт
    обещает другое: «что ни запросил - оно взяло и включилось», и показ обязан пережить
    обрыв интернета сам.

    Отсюда порядок: пока приёмник тёмный, LOAD в него не летит вовсе (у него своё
    терпение, и жечь его впустую нельзя) - ждём **факта**, а не таймера:

    * фильм лёг на диск целиком - сети не нужно вовсе, поднимаем сразу;
    * прогрев принёс новые куски - источник ожил, значит и сеть вернулась;
    * раздача снова читается (:attr:`Feed.offline` пуст) - то же самое;
    * источник, которого мы СПРОСИЛИ (:class:`torrcast.stream.Supply`), снова отвечает и
      снова знает нашу раздачу - её мы к этому моменту уже вернули магнитом.

    🔴 Все эти факты - про ИСТОЧНИК, и годятся они только для темноты, в которой источник
    виноват. Когда показ бросил сам приёмник (:attr:`dropped`), они выполнены с самого
    начала - прогрев растёт, пока жив TorrServer, - и первая попытка выстреливала в
    темноту нулевой длины, то есть сгорала впустую. В такой темноте ждут приёмник, а не
    куски, - и ровно столько, сколько ему нужно на самом деле: :data:`REVIVE_DROP` до
    первого LOAD (секунды, замер) и :data:`REVIVE_PAUSE` между остальными.

    🔴 Причина темноты берётся не из воздуха и не из пустого :attr:`Feed.offline`: прежде
    чем сказать «приёмник бросил показ», показ спрашивает источник. Трёхсекундный обрыв
    службы раздач не взводил в показе ровно ничего (ни счёт оборванных прогонов, ни часы
    молчания), и обвинение доставалось приёмнику - при живом, ни в чём не виноватом
    приёмнике и мёртвом источнике.

    Всё остальное - ограждения, и каждое кончается фолбэком «гаснем честно, а `cast`
    продолжит с места»: чужой показ на приёмнике не перебивается (:meth:`Receiver._free`),
    попыток не больше :data:`REVIVE_TRIES` на обрыв с выдержкой :data:`REVIVE_PAUSE`, а
    каждая темнота - не дольше :data:`REVIVE_LIMIT`. Запас попыток отмерян обрыву, а не
    сеансу, и возвращается только вместе с минутой живой картинки (:data:`REVIVE_LIVED`):
    иначе два коротких обрыва в начале фильма оставляли бы весь остаток вечера без защиты.

    🔴 Молча это ожидание не идёт. Оно - решение показа, а не пауза в работе: пока оно
    длится, на экране чёрное, и сказано об этом числом - в журнал каждые
    :data:`SAY_SECONDS` (сколько уже темно, из-за чего и через сколько показ сдастся) и
    отметкой в состоянии, откуда ту же правду берёт ``cast status``
    (:attr:`torrcast.state.Entry.dark`). Замер, из которого это выросло: с мёртвым
    источником юнит прожил 902 с, и всё это время «играю» отвечали и статус, и живой юнит.
    """

    #: С какого монотонного момента длится темнота; ``0.0`` - показ идёт.
    since: float = 0.0
    #: То же начало темноты, но стенным временем - метка для ЧУЖОГО процесса
    #: (:attr:`torrcast.state.Entry.dark`): монотонные часы за пределами своего процесса
    #: не значат ничего (:mod:`torrcast.timing`). Внутри показа по ней не ждут ни секунды,
    #: все выдержки по-прежнему меряет :attr:`clock`.
    began: float = 0.0
    #: Из-за чего погас показ (:meth:`_why`): та же строка, что ушла человеку и в след.
    #: Пусто - темноты нет. Хранится затем, чтобы правду говорил не только тот, кто был у
    #: консоли в секунду аварии: её повторяет и журнал показа, и ``cast status``.
    why: str = ""
    #: Сколько попыток подъёма потрачено на ТЕКУЩИЙ обрыв. Пережитый обрыв запас
    #: возвращает, но только вместе с доказательством - минутой живой картинки
    #: (:data:`REVIVE_LIVED`, :meth:`alive`).
    tries: int = 0
    #: Монотонное время последней попытки - от него отсчитывается :data:`REVIVE_PAUSE`.
    last: float = 0.0
    #: Сколько было прогрето, когда погасли: рост этого числа и есть «куски пошли».
    warmed: float = 0.0
    #: Источник показа или ``None`` (показ не из раздачи либо старый вызов). Спрашивается
    #: только отсюда и только в темноте: пока картинка идёт, вопросов источнику нет.
    supply: Supply | None = None
    #: Правда ли темнота случилась из-за ИСТОЧНИКА, а не приёмника: тогда и возврата ждём
    #: от источника, а не от :attr:`Feed.offline`, который в этом случае может быть пуст.
    blamed: bool = False
    #: Обратное: источника в этой темноте не винят вовсе - показ бросил сам приёмник
    #: (:meth:`_why`). Тогда ждать «куски пошли» бессмысленно, ждём ЕГО (:meth:`resurrect`).
    dropped: bool = False
    #: С какого монотонного момента показ снова идёт после темноты; ``0.0`` - либо темноты
    #: не было вовсе, либо запас попыток уже возвращён.
    back: float = 0.0
    #: Выдержка между попытками подъёма, секунды: мера молчания приёмника после 404
    #: (:attr:`torrcast.profile.Profile.revive_pause`). Умолчание - осторожный профиль.
    pause: float = REVIVE_PAUSE
    #: Выдержка до ПЕРВОЙ попытки в темноте, которую устроил сам приёмник, секунды: сколько
    #: ему нужно, чтобы снова взять LOAD (:attr:`torrcast.profile.Profile.revive_drop`).
    #: У разных приёмников она разная, поэтому приходит из профиля, а не из общей константы.
    #:
    #: ⚠️ Отсчёт - ОТ НАЧАЛА ТЕМНОТЫ, а не от приговора: прежде чем назвать виноватым
    #: приёмник, показ секунд шесть опрашивает источник (:data:`SOURCE_TRIES` вопросов с
    #: :data:`SOURCE_PAUSE`), и раньше конца этого опроса попытки быть не может вовсе -
    #: виновник ещё не назван. Значения меньше этих секунд потому сходятся в одно
    #: поведение - «сразу, как стало ясно, кто виноват» (живой замер: первая попытка
    #: вышла на 8.1 с, а не на 4.0). Это не сломанная ручка: собственный срок приёмника
    #: (3-4 с, замер) тоже идёт от начала темноты, и к концу опроса он уже истёк, а
    #: перенос отсчёта на момент приговора добавлял бы эти секунды чёрного экрана
    #: сверху - впустую, готовый приёмник ждал бы нас, а не мы его.
    drop: float = REVIVE_DROP
    #: Попытки закончились штатным фолбэком: позиция сохранена, показ можно продолжить.
    ended: bool = False
    #: Сколько показ должен идти живым, чтобы запас попыток снова считался полным.
    #: Меньше :attr:`pause` брать нельзя - см. :data:`REVIVE_LIVED`.
    lived: float = REVIVE_LIVED
    #: Чем меряется темнота и выдержка между попытками. Умолчание - настоящее время;
    #: сухой прогон подаёт свои часы (:class:`torrcast.timing.Clock`).
    clock: Clock = CLOCK

    def alive(self, shown: bool = True) -> None:
        """Показ идёт - темноте конец, а пережитый обрыв возвращает потраченный запас.

        Возвращает запас не сам факт подъёма, а прожитое после него время
        (:data:`REVIVE_LIVED`): «поднялся» говорит приёмник, а «обрыв позади» - только
        картинка, которая идёт и не гаснет. Замер, из которого это выросло: два коротких
        обрыва за 13 минут показа выбрали все три попытки, отмерянные на весь сеанс, -
        притом что каждый обрыв показ пережил и человек не заметил ничего.

        ``shown`` - на экране КАДР, а не ожидание его. ``BUFFERING`` темнотой не считается
        (показ жив, приёмник ждёт кусок), но и доказательством пережитого обрыва быть не
        может: картинки в нём нет ни секунды, а сторож подвиса в это время гонит указатель
        вперёд. Встала картинка - минуту живого показа считаем заново.
        """
        now = self.clock.monotonic()
        if self.since:
            self.since, self.blamed, self.dropped = 0.0, False, False
            self.began, self.why = 0.0, ""  # темноты нет - и отметки о ней тоже
            self.back = now  # темнота кончилась - засекаем прожитое
        if not self.back:
            return  # обрыва не было вовсе - и возвращать нечего
        if not shown:
            self.back = now
        elif now - self.back >= self.lived:
            self.back, self.tries = 0.0, 0

    def darkness(self) -> float:
        """Сколько длится темнота, секунды; ``0.0`` - на экране картинка.

        Отсюда правду о чёрном экране узнают оба, кто обязан её сказать: журнал показа
        (строка вместо «экран: … · IDLE») и через состояние - ``cast status``.
        """
        return self.clock.monotonic() - self.since if self.since else 0.0

    def resurrect(self, receiver: Receiver, feed: Feed, warmer: Warmer | None, pos: float) -> bool:
        """``True`` - показ ещё держим (ждём сеть или только что подняли), ``False`` - гаснем.

        ``pos`` - место, откуда поднимать: последняя позиция, которую приёмник успел
        назвать живой. Из мёртвой сессии её не взять - там ноль.
        """
        now = self.clock.monotonic()
        if not isinstance(receiver, _Revivable) or pos <= 0:
            return False  # поднимать нечем или неоткуда - это обычный конец показа
        if feed.duration > 0 and pos >= feed.duration * WATCHED_RATIO:
            return False  # фильм досмотрен: гаснущий экран тут и есть титры, а не авария
        if not self.since:
            self.since, self.warmed = now, warmer.warmed if warmer is not None else 0.0
            why = self._why(feed)
            self.began, self.why = time.time(), why
            trace.dark(pos=pos, why=why)
            print(
                f"показ погас на {_hms(pos)} ({why}) - подниму сам, как вернётся сеть",
                flush=True,
            )
        dark = now - self.since
        if self.tries >= REVIVE_TRIES or dark > REVIVE_LIMIT:
            print(
                f"показ поднять не удалось ({self.tries} попыт., темнота {dark:.0f} с) - "
                f"гашу; cast продолжит с {_hms(pos)}",
                flush=True,
            )
            self.ended = True
            return False
        if not self._may(feed, warmer, pos) or (self.last and now - self.last < self.pause):
            return True  # сети всё ещё нет либо выдержка между попытками не вышла
        if self.dropped and dark < self.drop:
            # 🔴 Показ бросил сам приёмник, источник цел - и признаки «сеть вернулась»
            # про приёмник не говорят ровно ничего. Прогрев в этот момент растёт всегда
            # (служба раздач жива, куски идут), :attr:`Feed.offline` пуст всегда - поэтому
            # первая попытка выстреливала в темноту нулевой длины и сгорала впустую.
            # Ждать тут можно одно - самого приёмника, а мера его молчания - время.
            #
            # ⚠️ Времени этого - секунды, а не минута: приёмник, бросивший показ, берёт
            # LOAD через 3-4 с (:data:`REVIVE_DROP`), и минута ожидания была минутой
            # чёрного экрана впустую. Осторожность живёт дальше по коду - в выдержке между
            # попытками со второй (:attr:`pause`), где она и заработана замером.
            return True
        self.tries, self.last = self.tries + 1, now
        came = "приёмник отмолчался" if self.dropped else "сеть вернулась"
        print(f"{came} - поднимаю показ с {_hms(pos)} (попытка {self.tries})", flush=True)
        ok = receiver.replay(pos)
        trace.revive(pos=pos, tries=self.tries, waited=dark, ok=ok)
        print(
            f"показ поднят с {_hms(pos)}"
            if ok
            else "приёмник показ не взял - жду ещё (или он занят чужим показом)",
            flush=True,
        )
        return True

    def _why(self, feed: Feed) -> str:
        """Из-за чего погас показ. Прежде чем винить приёмник, спрашиваем ИСТОЧНИК.

        Порядок именно такой. Приёмник гаснет молча и одинаково - и когда он сам исчерпал
        терпение, и когда ему нечего показывать, потому что источника не стало. Свои
        признаки показа тут не помощники: обрыв службы раздач на три секунды не взводит ни
        счёт оборванных прогонов, ни часы молчания (:data:`torrcast.stream.MUTE_SECONDS`), и
        :attr:`Feed.offline` остаётся пустым. Вопрос источнику стоит двух запросов и
        задаётся ровно один раз - в тот момент, когда показ уже признан погасшим.

        Причина возвращается одной строкой, и она же уезжает и в след, и человеку на
        экран: двух разных мнений о том, что случилось, быть не должно.
        """
        why_source = _blamed(self.supply, self.clock)
        if why_source:
            self.blamed = True
            if why_source != str(feed.offline):  # об одной аварии след пишет один раз
                trace.offline(why=why_source, asked=True)
            # Показ узнаёт причину от нас: дальше по ней живёт и упаковка (пробовать
            # реже, не умирать), и сам :class:`_Revival` (:meth:`_may`).
            feed.offline = why_source
            return why_source
        if feed.offline:
            return str(feed.offline)
        # Источник спрошен и здоров, упаковка на обрыв не жаловалась - винить некого,
        # кроме приёмника. Возврата в такой темноте ждут от него же (:meth:`resurrect`).
        self.dropped = True
        return "приёмник бросил показ"

    def _may(self, feed: Feed, warmer: Warmer | None, pos: float) -> bool:
        """Вернулась ли сеть - по факту, а не по часам.

        Прогретое сильнее любого признака сети: лежащий на диске фильм смотрится и без
        интернета вовсе, и ждать его возврата было бы враньём.

        Когда погасли из-за источника, спрашиваем ровно его же: :attr:`Feed.offline` в
        этом случае снимает только выложенный кусок, а выкладывать некому - упаковка ждёт
        запроса приёмника, а приёмник тёмен. Заодно это единственное место, где раздача
        возвращается магнитом: служба ответила - значит, самое время вернуть ей трекеры,
        и сделать это надо ДО того, как приёмник попросит поток по голому хэшу.
        """
        if warmer is not None:
            if warmer.done:
                return True
            if warmer.warmed > self.warmed:
                return True
        if self.blamed and self.supply is not None:
            if _asked(self.supply):
                return False  # источник всё ещё лежит - жечь терпение приёмника незачем
            feed.offline = ""
            self.why = "источник вернулся - жду готовности потока"
            # Ответ службы доказывает возврат источника, но не готовность потока. После
            # повторного добавления раздача ещё собирает метаданные и пиров; LOAD имеет
            # смысл лишь тогда, когда упаковка уже отдала кусок у сохранённой позиции.
            return feed.front(pos) > pos
        return not feed.offline


def _hold(
    receiver: Receiver,
    feed: Feed,
    watch: Watch | None = None,
    warmer: Warmer | None = None,
    supply: Supply | None = None,
    profile: Profile = CAUTIOUS,
    clock: Clock = CLOCK,
    journal: str = "",
) -> bool:
    """Держим показ: опрос приёмника раз в 2 с, упаковка должна быть жива, из RAM уходит
    только пройденное, сторож раз в 10 с пишет позицию.

    Перемотку здесь ловить больше нечем и незачем: приёмник видит весь фильм и на seek
    просто просит сегмент нужного места, а :class:`Feed` пакует оттуда.
    Показу остаётся то, о чём раздача не знает: пауза на пульте и конец показа.

    Придерживать ffmpeg сигналом (SIGSTOP) здесь больше нечем и незачем: темп держит
    сам ffmpeg (``-readrate`` + ``-readrate_initial_burst``), а под паузой процесс
    именно завершается — под SIGSTOP'ом приёмник намертво вис в BUFFERING.

    ``clock`` - чем меряются все выдержки показа (:class:`torrcast.timing.Clock`). Боевой
    путь ходит по настоящему времени; сухому прогону нужны свои часы, иначе тест выжидал
    бы терпение приёмника и выдержки между попытками подъёма по-настоящему.
    """
    paused, said, seen = 0.0, 0.0, False
    journal = journal or f"[сеанс {trace.session_id()}]"
    #: Позиция приёмника с прошлого опроса - от неё считается запас показа. Прошлая, а не
    #: сегодняшняя, потому что запас нужен раньше, чем приходит ответ приёмника, и взять
    #: его больше неоткуда. На решение сторожа это не влияет: нудж срабатывает только
    #: после :attr:`STALL_SECONDS` неподвижности, то есть когда прошлая позиция и есть
    #: сегодняшняя. А сразу после перемотки, где число ещё старое, позиция изменилась -
    #: и счётчик подвиса обнулён.
    last = 0.0
    #: Последний кадр, который человек ДЕЙСТВИТЕЛЬНО видел. Ровно оттуда показ и
    #: поднимают (:class:`_Revival`), и ровно он уходит в закладку «Продолжить?»:
    #: у мёртвой сессии позиции нет вовсе, там ноль.
    #:
    #: 🔴 ``BUFFERING`` в закладку не идёт, и это не придирка к состоянию: картинки на
    #: экране в нём нет, а позиция при этом двигается. Сторож подвиса
    #: (:meth:`torrcast.cast.ChromecastReceiver._nudge`) прыгает вперёд по 8 с, вытаскивая
    #: приёмник из зависания, и туда же смотрит повтор LOAD посреди показа. Замерено на
    #: живом Q70D: пока экран стоял на 2:39, сторож сделал 12 прыжков и увёл позицию на
    #: 4:15 - и показ воскресал с места, которого зритель не видел, ровно на 1:36 впереди
    #: последнего кадра. Сторож при этом прав, а закладка - нет: место показа отмеряет
    #: глаз, а не указатель.
    #:
    #: ``IDLE`` не идёт по другой причине: у мёртвой сессии позиции нет вовсе, там ноль.
    #: Всё остальное - показанный кадр: и пауза (на экране стоит он же), и честно
    #: доигранный конец входа. Штатная перемотка человеком тоже: после неё приёмник
    #: возвращается в ``PLAYING``, и первый же показанный кадр двигает закладку за ним.
    held = 0.0
    #: Позиция, на которой приёмник ВПЕРВЫЕ сказал ``PLAYING``; ``-1`` - ещё не говорил.
    #:
    #: 🔴 Слово состояния приходит раньше картинки, и разница не мелочь. Замер на живом
    #: Q70D (заход в тяжёлое место, сплошной перекод): приёмник отвечает ``PLAYING`` на
    #: 8.2-й секунде, а указатель стоит на месте захода ещё 6.0 с и трогается только
    #: тогда, когда показ выложил ВТОРОЙ кусок. Тот же прогон на другой сетке: ``PLAYING``
    #: на 10.4-й секунде, первый кадр - на 15.4-й. То есть каждое наше «старт NN с» было
    #: занижено на 5-6 с, и занижено ровно там, где человеку хуже всего - на тяжёлом месте.
    #: Отсюда правило: картинку доказывает ДВИЖЕНИЕ указателя, а не слово приёмника.
    still_at = -1.0
    show_trace = bool(os.environ.get(TRACE_ENV))
    buffering = was_offline = False
    # Обе выдержки воскрешения - мера молчания ПРИЁМНИКА, поэтому приходят из его профиля,
    # а не из общей константы: приставка после отказа берёт LOAD не так, как телевизор.
    revival = _Revival(
        supply=supply,
        pause=profile.revive_pause,
        lived=profile.revive_pause,
        drop=profile.revive_drop,
        clock=clock,
    )
    while True:
        _ctl(receiver)
        # Выкладка кусков стоит на пути запроса сегмента, а запросов может не быть вовсе:
        # показ, который берёт прогретое с диска, к упаковке не обращается, и написанное
        # ею копится в памяти (:meth:`torrcast.stream.Feed.sweep`). Поэтому её зовут ещё и
        # по часам показа - здесь, до всякого разговора с приёмником.
        feed.sweep()
        if trouble := feed.trouble():
            # 🔴 Упаковка сдалась - и вот теперь спрашиваем ИСТОЧНИК. Оборванные подряд
            # прогоны значат «показывать нечего» только при живом источнике; служба
            # раздач, которую перезапустили, рвёт вход так же, а ждать её три секунды.
            # Вопрос задаётся здесь, на краю показа, а не в горячем пути: раздача
            # сегментов не ждёт ни журнал, ни лишний запрос.
            why_source = _asked(supply)
            if why_source:
                feed.stall(why_source)  # показ не умирает, а ждёт возврата источника
                if not was_offline:  # говорим об аварии один раз, а не каждые две секунды
                    was_offline = True
                    trace.offline(why=why_source, asked=True)
                    print(
                        f"источник не читается ({why_source}) - жду его возврата, "
                        "показ подниму сам",
                        flush=True,
                    )
                clock.sleep(2.0)
                continue
            if supply is not None and supply.restored:
                # Источник вернулся ровно сейчас, и раздача у него снова с трекерами:
                # хоронить показ на этом месте было бы враньём - упаковка попробует ещё.
                feed.stall("")
                clock.sleep(2.0)
                continue
            # Убитый сигналом ffmpeg ничего сказать не успевает - не выдумываем за него.
            raise InfraError(f"упаковка оборвалась: {trouble}")
        try:
            # Запас упаковки идёт приёмнику: неподвижный BUFFERING при готовых сегментах
            # впереди - это зависание, а при пустых - законное ожидание нас.
            position = receiver.position(feed.front(last))
        except InfraError:  # приёмник позицию не отдаёт - показу остаётся только ждать
            clock.sleep(2.0)
            continue
        last = position.pos
        if position.pos > 0 and position.state not in {"BUFFERING", "IDLE"}:
            held = position.pos
        if not seen and position.state == "PLAYING":
            # Картинка на экране - теперь CLI имеет право сказать «старт NN с». Право это
            # даёт СДВИНУВШИЙСЯ указатель, а не слово ``PLAYING`` (см. :data:`still_at`):
            # приёмник объявляет себя играющим, ещё не набрав кадров, и на тяжёлом заходе
            # держит указатель на месте старта секунд шесть. Цена честности - один опрос
            # (2 с) запаса в худшую сторону; цена прежней доверчивости была 5-6 с в лучшую.
            if still_at < 0:
                still_at = position.pos
            elif position.pos > still_at:
                seen = True
                mark_playing(feed.out)
        # Ребуфер - только вход в BUFFERING, а не каждый опрос: иначе счётчик считал бы
        # секунды подвиса, а не сами подвисы. Сеть - на переходе в offline и обратно.
        if position.state == "BUFFERING" and not buffering:
            trace.emit("play", "buffering", pos=round(position.pos, 1))
        buffering = position.state == "BUFFERING"
        if bool(feed.offline) != was_offline:
            was_offline = bool(feed.offline)
            if was_offline:
                # Догадка, а не ответ источника: сюда приходят обрывы, замеченные самой
                # упаковкой (:meth:`torrcast.stream.Feed._survive`, :meth:`_mute`).
                trace.offline(why=str(feed.offline), asked=False)
        if show_trace:
            front = feed.front(position.pos)
            print(
                f"{journal} запас: показ {position.pos:.0f} · упаковано {front:.0f} · "
                f"впереди {front - position.pos:.0f} с · {feed.weight() / 1e6:.0f} МБ · "
                f"расхождение с манифестом {feed.drift():.3f} с · {position.state}",
                flush=True,
            )
        if warmer is not None:
            # Приоритет живого окна держится ровно здесь: прогрев видит тот же запас, что
            # и сторож приёмника, и на просевшем замирает (:meth:`torrcast.warm.Warmer._throttle`).
            warmer.feed(feed.front(position.pos) - position.pos)
            if warmer.done and feed.rest():
                print("прогрето целиком - живую упаковку гашу, показ идёт с диска", flush=True)
        if clock.monotonic() - said >= SAY_SECONDS:
            said = clock.monotonic()
            if dark := revival.darkness():
                # 🔴 Темнота - не «показ с неподвижным указателем». Отчитываться в ней
                # позицией и запасом («экран: 0:01:12 · IDLE», «показ обеспечен до
                # 0:01:12») значит называть чёрный экран показом: кадра на нём нет ни
                # одного, а числа те же, что и у живой картинки. Поэтому строка тут своя,
                # и в ней сказано ровно то, что показ решил сам: сколько уже темно, из-за
                # чего и когда он сдастся, если источник не вернётся.
                # ⚠️ Ноль попыток в темноте - это не сломанный счётчик, а решение: пока
                # источник лежит, LOAD в приёмник не летит вовсе (:meth:`_Revival._may`).
                # Молча это выглядело как бездействие, и на потолке человек получал
                # «0 попыт.» без единого объяснения, откуда он взялся.
                spent = (
                    f"поднимал {revival.tries} из {REVIVE_TRIES}"
                    if revival.tries
                    else "источник не вернулся - приёмник не трогаю"
                )
                print(
                    f"{journal} темнота {_hms(dark)} ({revival.why}) - картинки нет; "
                    f"{spent}, погашу через {_hms(REVIVE_LIMIT - dark)}",
                    flush=True,
                )
            else:
                # Что видит приёмник, тем и отчитываемся: длительность и позиция - это
                # ровно ``duration`` и ``current_time`` из MEDIA_STATUS, снятые владеющим
                # сендером. Другого доказательства «на ТВ есть таймлайн» у нас нет.
                print(
                    f"{journal} экран: {_hms(position.pos)} из {_hms(position.dur)} · "
                    f"{position.state}",
                    flush=True,
                )
                if feed.offline:
                    # Обрыв длиннее прогретого не имеет права быть молчаливой смертью:
                    # показ говорит, докуда он обеспечен, и продолжает пробовать сеть. В
                    # темноте эта строка не печатается: обеспечивать там уже нечего.
                    print(
                        f"сети нет ({feed.offline}) - показ обеспечен до "
                        f"{_hms(feed.front(position.pos))}",
                        flush=True,
                    )
            if warmer is not None:
                print(warmer.line(), flush=True)
        if watch is not None:
            # Прогрев виден снаружи только через состояние: живой показ из другого
            # процесса не спросишь (:attr:`torrcast.state.Entry.warm`).
            if warmer is not None:
                watch.entry.warm = warmer.warmed
            # В закладку уходит показанный кадр, а не указатель приёмника: пока экран
            # стоит, сторож подвиса гонит указатель вперёд, и «Продолжить?» звало бы
            # человека туда, где он не был (см. ``held``).
            watch.see(held)
            # Тем же каналом наружу уходит и правда о чёрном экране: живой юнит показа не
            # доказывает (:attr:`torrcast.state.Entry.dark`). Пишется она не по тику
            # сторожа, а сразу на переходе - врать «играю» лишние десять секунд не за что.
            if (watch.entry.dark, watch.entry.dark_why) != (revival.began, revival.why):
                watch.entry.dark, watch.entry.dark_why = revival.began, revival.why
                watch.flush()
            if watch.done and watch.entry.serial:
                return False  # серия досмотрена - освобождаем показ под следующую
        if position.state == "PAUSED":
            paused = paused or clock.monotonic()
            if clock.monotonic() - paused > PAUSE_LIMIT:
                return False  # пауза длиной с вечер - показ окончен, юнит гасим
            if clock.monotonic() - paused > PAUSE_SECONDS and not feed.halted():
                print("пауза на пульте - упаковку гашу", flush=True)
                feed.halt()  # вернутся к показу - раздача сама начнёт паковать заново
        elif not position.playing:
            # Показ погас. Это конец только тогда, когда поднять его не удалось: обрыв
            # интернета длиннее приёмникова терпения гасит экран, а фильм и место, где
            # его смотрели, никуда не делись (:class:`_Revival`).
            if not revival.resurrect(receiver, feed, warmer, held):
                return revival.ended
            # Причину темноты добывает сам :class:`_Revival`, спрашивая источник, и в след
            # она уже легла (:meth:`_Revival._why`). Второй раз то же событие не пишем.
            was_offline = bool(feed.offline)
        else:
            # Кадр на экране или ожидание его - разница тут в том же, в чём и у ``held``:
            # запас попыток возвращает прожитая картинка, а не прожитый BUFFERING.
            revival.alive(position.state == "PLAYING")
            paused = 0.0
            if feed.recoder is not None:
                feed.recoder.played = position.pos
            feed.prune(position.pos)
        clock.sleep(2.0)


__all__ = [name for name in globals() if not name.startswith("__")]
