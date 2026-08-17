"""Сценарий запуска и сопровождения выбранного показа."""

# ruff: noqa: F821, F822, N806

from __future__ import annotations

from torrcast.domain._name_data.data_3 import VIDEO_EXT
from torrcast.domain.codec_name import codec_name
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.recode_note import recode_note
from torrcast.domain.recodes_whole import recodes_whole
from torrcast.domain.release import Release
from torrcast.domain.revive_settings import (
    REVIVE_DROP,
    REVIVE_LIMIT,
    REVIVE_LIVED,
    REVIVE_PAUSE,
    REVIVE_TRIES,
)
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.why import why
from torrcast.ports.journal import journal
from torrcast.ports.progress import Progress
from torrcast.ports.progress import progress as progress_bar
from torrcast.usecases.episode_duration import WORKER_DUR
from torrcast.usecases.following import _following
from torrcast.usecases.revive_playback import _hold, _Revival
from torrcast.usecases.select import _about, _Plan
from torrcast.usecases.source_blame import _asked, _blamed
from torrcast.usecases.start_budget import START_BUDGET
from torrcast.usecases.start_clock import _Clock
from torrcast.usecases.warm import Vault, Warmer, warm_key, warm_root
from torrcast.usecases.watch import Watch

# fmt: off
__all__ = [
    "CAUTIOUS", "CLOCK", "ENDING_RATIO", "EXIT_OK",
    "REVIVE_DROP", "REVIVE_LIMIT", "REVIVE_LIVED",
    "REVIVE_PAUSE", "REVIVE_TRIES", "START_BUDGET",
    "TYPE_CHECKING", "VIDEO_EXT",
    "Any", "Callable", "ChromecastReceiver",
    "Clock", "Config", "Encode",
    "Entry", "Feed", "Grid",
    "HlsServer", "InfraError", "NoReturn",
    "NotFoundError", "Path", "Profile",
    "Progress", "Receiver", "Recoder",
    "Release", "StartRefusedError", "State",
    "Supply", "TorrcastError", "TorrFile",
    "TorrServer",
    "Vault", "Warmer",
    "_Revival", "_asked", "_await_playing",
    "_blame_the_end", "_blamed", "_default_file",
    "_encode_all", "_file_picker", "_handover",
    "_hold", "_launch", "_layout",
    "_next_warmer", "_play", "_recoder",
    "_refuse_hopeless", "_resume", "_warmer",
    "ask_line", "codec_name", "contextlib",
    "dataclass", "detect_profile", "forget_playing",
    "hls_base", "make_receiver",
    "mark_playing", "os", "pick_video_file",
    "playing_flag", "probe", "recode_note",
    "recodes_whole", "start_play_unit",
    "time",
    "warm_file",
    "warm_key", "warm_root", "whole_encode",
    "why",
]
# fmt: on

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


import contextlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from torrcast.domain.entry import ENDING_RATIO
from torrcast.ports.module import module
from torrcast.ports.show_unit import ShowUnit
from torrcast.ports.show_unit import unit as show_unit
from torrcast.ports.stream_source import StreamSource

clock_port = module("time")
time = clock_port
for _module_name, _names in {
    "torrcast.cast": (
        "ChromecastReceiver",
        "Receiver",
        "make_receiver",
    ),
    "torrcast.console": ("ask_line",),
    "torrcast.recode": (
        "Encode",
        "Recoder",
        "whole_encode",
    ),
    "torrcast.state": ("State",),
    "torrcast.stream": (
        "Feed",
        "Grid",
        "HlsServer",
        "Supply",
        "TorrServer",
        "forget_playing",
        "hls_base",
        "mark_playing",
        "pick_video_file",
        "playing_flag",
        "probe",
        "start_play_unit",
        "warm_file",
    ),
    "torrcast.timing": (
        "CLOCK",
        "Clock",
    ),
}.items():
    _dependency = module(_module_name)
    globals().update({name: getattr(_dependency, name) for name in _names})
detect_profile = module("torrcast.profile").detect


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


def _resume(config: Config, key: str, entry: Entry, clock: _Clock, dry: bool = False) -> int:
    """Молча продолжить с записанных релиза, файла, дорожки и позиции.

    Прежний прогрев позиции имел полезное время только пока человек отвечал на теперь
    удалённый вопрос. После запуска он конкурировал бы с ffmpeg за тот же рой, поэтому
    молчаливое продолжение сразу передаётся владельцу показа.
    """
    journal().mark("ответы")  # ноль секундомера: на этом пути вопросов нет
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
    show_unit().stop()
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
    journal().mark("юнит")
    with progress_bar() as progress:
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


def _await_playing(
    config: Config,
    progress: Progress,
    timeout: float = START_BUDGET,
    clock: Clock = CLOCK,
    unit: ShowUnit | None = None,
) -> None:
    """Дождаться **картинки на экране**, а не «упаковка пошла».

    Две разные вещи, которые легко счесть одной: первый сегмент в tmpfs — это упаковка, а
    картинка — это приёмник, ответивший ``PLAYING``. Спросить приёмник отсюда нельзя:
    сендер к нему должен быть ровно один, и он живёт в юните (см. :mod:`torrcast.cast`).
    Поэтому юнит кладёт флажок (:func:`mark_playing`), а CLI его ждёт — и печатает
    «старт NN с» ровно в тот момент, когда на экране появилось изображение.

    ``clock`` и ``unit`` - выдержка ожидания и сам юнит показа
    (:class:`torrcast.ports.show_unit.ShowUnit`). Боевой путь ждёт настоящими секундами и
    спрашивает тот юнит, что поставил композиционный корень; сухому прогону дают свои
    часы и свой юнит прямо здесь, иначе тест выжидал бы весь бюджет старта по-настоящему.
    """
    unit = unit if unit is not None else show_unit()
    out = Path(config.hls_dir)
    flag = playing_flag(out)
    deadline = clock.monotonic() + timeout
    packed = False
    while clock.monotonic() < deadline:
        if flag.exists():
            journal().mark("картинка")
            progress.phase("")
            return
        if not packed:
            with contextlib.suppress(OSError):
                packed = any(out.glob("v*.ts"))
            if packed:
                journal().mark("первый сегмент")
        progress.phase("жду телевизор" if packed else "упаковка")
        if not unit.active():
            progress.phase("")
            raise InfraError(f"показ не запустился: {unit.why()}")
        clock.sleep(0.2)
    progress.phase("")
    unit.stop()
    raise InfraError(f"показ не начался за {timeout:.0f} с - {unit.why()}")


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
    Encode, Recoder, Weights = (
        getattr(module("torrcast.recode"), name) for name in ("Encode", "Recoder", "Weights")
    )
    AUDIO_MBIT, TS_OVERHEAD, film_keys = (
        getattr(module("torrcast.stream"), name)
        for name in ("AUDIO_MBIT", "TS_OVERHEAD", "film_keys")
    )

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
    MAXRATE_GAIN = module("torrcast.recode").MAXRATE_GAIN
    AUDIO_MBIT, TS_OVERHEAD, grid_for = (
        getattr(module("torrcast.stream"), name)
        for name in ("AUDIO_MBIT", "TS_OVERHEAD", "grid_for")
    )

    whole = _encode_all(config, codec, video_mbit, depth, profile, frame, hdr)
    grid = grid_for(
        source,
        length,
        config.hls_segment,
        config.hls_keyframes,
        say=say,
        delivered_mbit=(video_mbit + AUDIO_MBIT) * TS_OVERHEAD if video_mbit > 0 else 0.0,
        ceiling_mbit=(
            (config.recode_mbit * MAXRATE_GAIN + AUDIO_MBIT) * TS_OVERHEAD if config.recode else 0.0
        ),
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
    (:func:`probe` - длительность для порога перехода) и карта опорных кадров
    (:func:`torrcast.stream.film_keys` - сетка и манифест). Посреди обрыва связи спросить
    их не у кого, и показ, у которого следующая серия ЛЕЖИТ на диске, всё равно уткнулся
    бы в мёртвую раздачу. Здесь оба вопроса задаются заранее и оба ложатся в кэш на диск.

    ``None`` - греть нечего: фильм, последняя серия раздачи или запись без списка серий.
    """
    RECODE_DIR = module("torrcast.recode").RECODE_DIR
    hls_dir = module("torrcast.stream").hls_dir

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
    journal().plan(
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
    supply: StreamSource | None = None,
    profile: Profile = CAUTIOUS,
    frame: int = 0,
    hdr: bool = False,
    session_tag: str = "",
) -> int:
    """Упаковка → раздача по http на голом IP → приёмник. Своих демонов нет: и ffmpeg,
    и раздача живут ровно на время показа и гасятся вместе с ним, что бы ни случилось.

    Упаковка за показ перезапускается столько раз, сколько человек перемотал: манифест
    обещает приёмнику весь фильм, а :class:`Feed` пакует то место, которое он попросил.
    Раздача, приёмник и LOAD при этом одни на весь показ.

    ``follow`` - чем прогреву заняться, когда эта серия ляжет на диск целиком
    (:attr:`torrcast.warm.Warmer.follow`); у фильма его нет и быть не может.

    ``supply`` - источник показа (:class:`torrcast.ports.stream_source.StreamSource`): служба и наша
    раздача в ней. Спрашивают его только на краю показа, зато прежде, чем объявить показ
    погасшим, - иначе за аварию источника отвечает приёмник, который ни при чём.

    ``profile`` - пороги ПРИЁМНИКА (:mod:`torrcast.profile`): вес куска, терпение, сторож
    нуджей, удержание запроса вместо 404. Умолчание осторожное - тот же Q70D, что и был.
    """
    RECODE_DIR = module("torrcast.recode").RECODE_DIR
    hls_dir = module("torrcast.stream").hls_dir

    out = hls_dir(config.hls_dir)
    start = watch.entry.pos if watch else 0.0
    length = watch.entry.dur if watch else duration
    tls = config.transport == "https"
    video_mbit = max(0.0, watch.entry.vbps) if watch else 0.0
    session_tag = session_tag or f"[сеанс {journal().session_id()}]"
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
    journal().mark("сетка", сегментов=grid.count, покадрам=grid.on_keys)
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
        journal().mark(
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
        journal().mark("раздача")
        # Упаковку начинаем сами, не дожидаясь первого запроса: ресиверу нужен готовый
        # кусок сразу, иначе LOAD упирается в ожидание ffmpeg и старт растёт на глазах.
        if recoder is not None:
            recoder.played = start
            recoder.start()
        feed.restart(grid.slot_at(start))
        journal().mark("упаковка пошла")
        raised = True
        try:
            receiver.play(url, about, at=start)
        except StartRefusedError as exc:
            # 🔴 Отказ на первом LOAD показ больше не хоронит. Приёмник в сети, фильм на
            # месте, упаковка идёт - и единственное, чего не хватает, это ещё одного
            # захода в чистое приложение. Ровно это умеет лестница воскрешения, и она же
            # чинит такой отвал посреди фильма (:meth:`_Revival.resurrect`): показ,
            # которого не было, поднимается тем же путём, что и погасший.
            # ⚠️ Ловится именно отказ ЗАГРУЗКИ, а не любая авария: приёмника нет в сети -
            # это другая беда и другой класс (:class:`torrcast.cast_core.StartRefusedError`),
            # и висеть с ней перед пустым экраном весь бюджет старта незачем.
            raised = False
            print(f"{session_tag} {why(exc)} - поднимаю показ сам", flush=True)
        else:
            journal().mark("LOAD взят")
            print(f"{session_tag} играю {about} - на ТВ   (старт {clock.total:.0f} с)", flush=True)
        # ⚠️ Прогрев стартует ровно ЗДЕСЬ и ни строкой выше: путь до картинки он не
        # удлиняет ни на секунду - ни своим ffmpeg, ни чтением каталога. Всё, что он
        # делает, происходит уже при играющем показе и на остатке процессора.
        if warmer is not None:
            warmer.start()
        expected_end = _hold(
            receiver,
            feed,
            watch,
            warmer,
            supply,
            profile,
            session_tag=session_tag,
            start=start,
            raised=raised,
        )
    finally:
        # Позиция фиксируется при любом исходе, включая SIGTERM, и делается это ПЕРВЫМ
        # делом: показ, доигранный до конца файла, отмечает «досмотрено» ровно здесь, а
        # приёмнику ниже нужно уже готовое состояние - по нему он и узнаёт, конец это
        # показа или стык серий.
        if watch is not None:
            watch.close()
            journal().emit(
                "session",
                "session_end",
                pos=round(watch.entry.pos, 1),
                dur=round(watch.entry.dur, 1),
                watched=bool(watch.done),
            )
        if warmer is not None:
            warmer.stop()
            # Досмотрено - прогретое стирается: держать на диске фильм,
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
    if report is not None:
        print(f"{session_tag} {report.line()}")
    # 🔴 Показ, не давший НИ ОДНОГО кадра, обязан назвать себя вслух - и раньше всего
    # прочего. Лестница воскрешения к этой строке уже отработала своё
    # (:meth:`_Revival.resurrect`), и раз кадра всё равно нет, молчаливый выход юнита -
    # это чёрный экран без единого слова. На стыке серий он же и самый дорогой: консоли
    # там нет вовсе, а сеанс до сих пор кончался кодом 0 и пустотой в журнале.
    # ⚠️ Живой приёмник цифр приёмки не считает (``report`` есть только у сухого), так
    # что до этой правды путь показа на живом ТВ не доходил вообще ничем.
    if watch is not None and not watch.seen and not watch.done:
        _blame_the_end(supply, shown=False)
    if report is None:
        return EXIT_OK
    # Досмотренный показ виноватого не ищет: хвост упаковки декодеру отдали, а недобор
    # сегментов на самом конце - это конец файла, а не авария.
    if not report.ok and not expected_end and not (watch is not None and watch.done):
        _blame_the_end(supply)
    return EXIT_OK


def _handover(watch: Watch | None) -> bool:
    """Правда ли показ передают следующей серии, а не заканчивают.

    Порог перехода уже записал в состояние следующую серию (:meth:`Watch.close`), поэтому
    ответ лежит там же, где его читает :func:`_cmd_worker`, — двух разных мнений о конце
    показа быть не должно.
    """
    return watch is not None and watch.done and _following(watch.key) is not None


def _blame_the_end(
    supply: StreamSource | None, shown: bool = True, clock: Clock = CLOCK
) -> NoReturn:
    """Показ кончился недосмотренным - назвать виноватого, и назвать верно. Всегда бросает.

    🔴 Последняя строка показа - последняя возможность сказать правду. Раньше показ
    кончался обвинением «приёмник не досмотрел поток» при живом приёмнике и мёртвой
    службе раздач. Замерено на стенде: перезапуск службы под показом давал ровно эту
    строку, и про источник в ней не было ни слова.

    ``shown`` - видел ли зритель хоть один кадр. Разница не косметическая: «не досмотрел»
    и «не увидел вовсе» - это две разные аварии для того, кто сидит перед экраном, и
    вторая стоит выше на лестнице цели. Сюда она доходит только исчерпав лестницу
    воскрешения: показ, не давший кадра, сперва поднимают, и лишь потом хоронят.

    Спросить источник тут можно спокойно: показ уже кончился, горячего пути нет, а
    человеку и следу уходит одна и та же причина.
    """
    why_source = _blamed(supply, clock)
    if why_source:
        journal().offline(why=why_source, asked=True)
        if not shown:
            raise InfraError(f"картинки не было ни разу: источник не читается ({why_source})")
        raise InfraError(f"источник не читается ({why_source}) - показ оборван, цифры выше")
    if not shown:
        raise InfraError("картинки не было ни разу: приёмник не взял показ - поднять не удалось")
    raise InfraError("приёмник не досмотрел поток - цифры выше")
