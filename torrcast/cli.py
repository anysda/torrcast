"""CLI — единственный наш процесс (§3 ТЗ).

Контракт (§5 v1 + §2 SPEC-v2): ``cast <запрос> [sNeM] [--new] [--dry]``, отладочные
ручки ``--release N`` / ``--file N`` / ``--voice N`` / ``cast releases <запрос>`` /
``cast voices <запрос>``, а также ``cast stop``, ``cast status``, ``cast doctor``,
``cast --tv <ip>``. Коды выхода: ``0`` ок · ``1`` не нашли · ``2`` инфра-ошибка;
наружу — короткие русские строки без трейсбеков (§6).

Счастливый путь §2 SPEC-v2 (с правкой владельца 06-08) — **один вопрос** и ни одного
упоминания файлов: «какой фильм франшизы?», и тот пропускается, когда картина одна.
Релиз и озвучка выбираются сами, о выборе говорится вслух, а таблица релизов, список
файлов и меню озвучек уезжают в отладочные ручки. Второй вопрос бывает ровно один —
«Продолжить?» у начатой картины (§2.3 v1): он про намерение, а не про технику.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import signal
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from torrcast import (
    InfraError,
    NotFoundError,
    TorrcastError,
    __version__,
    console,  # через модуль: терминал спрашиваем там же, где и сами вопросы
    why,
)
from torrcast.cast import ChromecastReceiver, Receiver, make_receiver
from torrcast.console import Progress, ask, ask_line, terminal
from torrcast.parse import (
    VIDEO_EXT,
    Episode,
    EpisodeFile,
    Picture,
    Release,
    map_episodes,
    slugify,
    split_episode,
    split_franchise_index,
)
from torrcast.recode import Recoder
from torrcast.search import Prowlarr, to_releases
from torrcast.state import Config, Entry, State, load_config, save_config
from torrcast.stream import (
    KEYS_WAIT,
    PILOT_TIMEOUT,
    Feed,
    Grid,
    HlsServer,
    Media,
    TorrFile,
    TorrServer,
    bitrate_mbit,
    forget_playing,
    hls_base,
    mark_playing,
    pick_video_file,
    playing_flag,
    probe,
    start_play_unit,
    stop_play_unit,
    unit_active,
    unit_key,
    unit_why,
    warm_file,
)
from torrcast.timing import mark

__all__ = [
    "Args",
    "bitrate_of",
    "honest_shot",
    "is_dated",
    "liveliest",
    "liveliness",
    "main",
    "parse_args",
    "pick_voice",
    "promises_more",
    "quality_text",
    "rank_releases",
    "render_table",
    "understated",
    "voices_table",
    "warm_order",
]

EXIT_OK, EXIT_NOT_FOUND, EXIT_INFRA = 0, 1, 2
#: Сколько строк таблицы релизов показываем: ниже начинаются раздачи без сидов.
TABLE_LIMIT = 12
#: Сколько релизов подряд проверяем ffprobe, прежде чем сдаться (§1: подмены не молчат).
MAX_TRIES = 3
#: ``--voice`` без номера: показать меню озвучек. Ноль тут свободен — дорожки для
#: человека нумеруются с единицы.
VOICE_MENU = 0
#: Сколько картин франшизы греем под меню: топ-2–3 релиза уходят в TorrServer фоном,
#: пока человек отвечает на вопросы (§4 SPEC-v2).
PREWARM = 3
#: Бюджет одной раздачи на метаданные по DHT, секунды. Не уложилась — не «зависли
#: насмерть», а честная строка и следующий релиз (дефект №1 владельца, §1 SPEC-v2).
META_BUDGET = 20.0
#: Бюджет на чтение дорожек (ffprobe) той же раздачи, секунды.
PROBE_BUDGET = 40.0
#: Сколько ждём ответа от честного запасного, если верх оказался хуже, чем обещал. Запасной
#: к этой секунде уже греется (:meth:`_Bench.resolve` поднимает следующего сразу), так что
#: платим не за прогрев, а за разницу между двумя ffprobe. Не уложился — играем то, что
#: есть, и говорим об этом вслух: лишние секунды старта хуже, чем 574p (§4 SPEC-v2).
HONEST_BUDGET = 12.0
#: Ниже этой высоты кадра HD уже не назовёшь. Имя раздачи о разрешении молчит чаще, чем
#: врёт (у «Моаны 2» — в 5 именах из 11), поэтому «имя молчало, а внутри SD» — такой же
#: повод посмотреть на соседа, как и прямое враньё в имени.
HD_HEIGHT = 720
#: Насколько подтверждённая высота вправе отставать от заявленной. 0.9 — это про обрезку
#: чёрных полей: у 1080p-широкоформатника реальная высота 800–816, и релиз честен. А
#: 574 против 1080 — это уже другая ступень лестницы, а не кадрирование.
HONEST_RATIO = 0.9
#: Потолок ожидания метаданных раздачи **в юните**, секунды. Здесь это не «бюджет фазы
#: под меню» (:data:`META_BUDGET`), а последний рубеж: магнит юниту уже дали, и если
#: метаданные не приехали, показывать нечего.
WORKER_META = 60.0
#: Потолок ffprobe длительности в юните: своей длительности следующая серия не знает, и
#: читается она из потока (:func:`_duration`).
WORKER_DUR = 90.0
#: Прочее на пути юнита до картинки, у чего своего потолка нет: запуск transient-юнита,
#: чтение состояния, подъём раздачи. Секунды, но считать их нулём — врать себе.
START_SLACK = 10.0
#: **Бюджет старта показа: столько CLI ждёт картинку на экране** (:func:`_await_playing`).
#:
#: Число не выбирается на глаз и не «берётся с запасом»: это сумма потолков всех фаз,
#: которые юнит проходит от запуска до первого ``PLAYING``, — метаданные раздачи, ffprobe
#: длительности, ожидание чужой карты опорных кадров, пробный прогон упаковки и терпение
#: приёмника к молчаливому ``IDLE``. Пока CLI ждал меньше суммы (120 с против 60 + 90 +
#: 60), он гасил `stop_play_unit`'ом показ, который вот-вот начался бы, — §7.4 SPEC-v2.
#:
#: Ждать так долго не страшно и не молчаливо: :class:`~torrcast.console.Progress` всё это
#: время показывает живую фазу, а любая честная неудача убивает юнит раньше — CLI видит
#: это по :func:`unit_active` и печатает причину из журнала, не досиживая до конца.
START_BUDGET = (
    WORKER_META
    + WORKER_DUR
    + KEYS_WAIT
    + PILOT_TIMEOUT
    + START_SLACK
    + ChromecastReceiver.START_TIMEOUT
)
#: Как часто сторож кладёт позицию в state, секунды (§3).
WATCH_SECONDS = 10.0
#: Как часто показ пишет в журнал, что видит приёмник (§2.1 SPEC-v2): позиция и общее
#: время — единственное доказательство того, что на экране есть таймлайн (§9).
SAY_SECONDS = 30.0
#: ``TORRCAST_TRACE=1`` — писать в журнал запас показа на каждом опросе (раз в 2 с):
#: позиция приёмника, край упаковки, разница между ними и вес tmpfs. Это инструмент §6
#: SPEC-v2: провал устойчивости видно только в динамике запаса, а раз в 30 с он теряется.
TRACE_ENV = "TORRCAST_TRACE"
#: ``TORRCAST_CTL=<файл>`` — диагностический пульт показа: строка в файле («``seek 1200``»,
#: «``pause``», «``play``») исполняется владеющим сендером на ближайшем опросе, файл
#: съедается. Нужен ровно затем, что кнопку на пульте может нажать только человек, а
#: вторым pychromecast команду не подать вовсе: приёмник считает второе соединение тем же
#: сендером и отвечает пустым MEDIA_STATUS (докстринг :class:`ChromecastReceiver`).
#: Приёмнику это приходит той же MEDIA-командой, что и с пульта, поэтому проверка честная.
#: На счастливом пути не участвует: переменной нет — кода нет.
CTL_ENV = "TORRCAST_CTL"
#: Сколько терпим паузу на пульте, прежде чем погасить упаковку (§6 SPEC-v2): дальше
#: сегменты копились бы в tmpfs впустую — приёмник их не забирает.
PAUSE_SECONDS = 60.0
#: Пауза длиннее этого — показ считается оконченным: юнит гаснет и не держит раздачу.
PAUSE_LIMIT = 3600.0
#: Битрейт, ниже которого раздача без единого маркера качества в имени — это SD-рип
#: (MPEG-4 в .avi), а не скромный 1080p. Порог выбран по замеру, а не на глаз: из 264
#: раздач живой выдачи («моана», «тачки», «матрица», «интерстеллар», «аватар») удалось
#: достать .torrent и заглянуть внутрь у 36. Все восемь .avi в этой выборке не называют
#: ни разрешения, ни кодека, и у пяти полнометражных потолок вышел 3.5 Мбит/с; ближайший
#: снизу подтверждённый .mkv с такой же безымянной шапкой — 5.4 Мбит/с. Порог поставлен
#: посередине этого зазора.
SD_BITRATE = 4.0
#: Признаки образа диска в имени раздачи — внутри VOB/BDMV, а не один файл.
_DISC_RE = re.compile(
    r"\b(?:video_?ts|bdmv|dvd[- ]?video|dvd[59]|iso|blu-?ray\s*(?:disc|cee)|avc\+?\s*iso)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class Args:
    query: list[str]
    tv: str | None = None
    release: int | None = None
    file: int | None = None
    #: ``--voice N`` — играть дорожку N; ``--voice`` без номера (:data:`VOICE_MENU`) —
    #: показать меню озвучек и спросить. На счастливом пути обоих нет: озвучка
    #: выбирается сама (правка владельца 06-08 к §2 SPEC-v2).
    voice: int | None = None
    new: bool = False
    dry: bool = False
    #: Внутреннее: показ внутри transient-юнита, руками не зовётся.
    play_key: str | None = None

    @property
    def command(self) -> str:
        """``stop`` / ``status`` / ``doctor`` / ``releases`` / ``voices`` / ``play`` /
        ``configure`` / ``worker``.
        """
        if self.play_key:
            return "worker"
        if self.query and self.query[0] in {"stop", "status", "doctor", "releases", "voices"}:
            return self.query[0]
        if not self.query:
            return "configure" if self.tv else "status"
        return "play"

    @property
    def episode(self) -> Episode | None:
        """Явно указанная серия: ``cast киберпанк s2e5``, ``2x5``, «2 сезон 5 серия» (§2.4)."""
        return split_episode(" ".join(self.query))[1]

    @property
    def title_query(self) -> str:
        """Запрос без указания серии: искать надо «киберпанк», а не «киберпанк 2x5»."""
        return split_episode(" ".join(self.query))[0]

    @property
    def pinned(self) -> bool:
        """Релиз или файл названы руками — отладочный путь, подмен в нём не бывает."""
        return self.release is not None or self.file is not None


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """Разобрать argv по контракту §5."""
    about = "torrcast — найти релиз и кастить его на ТВ без скачивания"
    parser = argparse.ArgumentParser(prog="cast", description=about, allow_abbrev=False)
    parser.add_argument("query", nargs="*", help="название, либо stop / status")
    parser.add_argument("--tv", metavar="IP", help="разовая настройка адреса ТВ (или mock)")
    parser.add_argument("--release", type=int, metavar="N", help="отладка: взять релиз N")
    parser.add_argument("--file", type=int, metavar="N", help="отладка: взять файл N раздачи")
    parser.add_argument(
        "--voice",
        type=int,
        nargs="?",
        const=VOICE_MENU,
        metavar="N",
        help="озвучка: N — взять дорожку N и запомнить, без номера — меню",
    )
    # Прежнее имя того же флага: ломать чужие пальцы и историю оболочки незачем.
    parser.add_argument(
        "--audio", type=int, nargs="?", const=VOICE_MENU, dest="voice", help=argparse.SUPPRESS
    )
    parser.add_argument("--new", action="store_true", help="забыть прогресс и выбрать заново")
    parser.add_argument("--dry", action="store_true", help="весь резолв без каста")
    parser.add_argument("--play-key", metavar="KEY", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"torrcast {__version__}")
    return Args(**vars(parser.parse_args(argv)))


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входа console-script ``cast``."""
    # Прогресс идёт вперемешку с ошибками в stderr: без построчного сброса врёт порядок.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)
    try:
        args = parse_args(argv)
        command = args.command
        # IUTF8 на stdin включаем на всё время команды и возвращаем режим как было (§3
        # SPEC-v2): без него ssh-сессия владельца ломает кириллицу в вопросах.
        with terminal():
            if command == "configure":
                return _cmd_configure(args)
            if command == "stop":
                return _cmd_stop()
            if command == "status":
                return _cmd_status()
            if command == "doctor":
                return _cmd_doctor()
            if command == "releases":
                return _cmd_releases(args)
            if command == "voices":
                return _cmd_voices(args)
            if command == "worker":
                return _cmd_worker(str(args.play_key))
            return _cmd_play(args)
    except NotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_NOT_FOUND
    except TorrcastError as exc:  # InfraError и всё прочее наше
        print(str(exc), file=sys.stderr)
        return EXIT_INFRA
    except _Stopped:  # `cast stop` — штатный конец показа, а не отказ (§7.4 SPEC-v2)
        return EXIT_OK
    except KeyboardInterrupt:
        return EXIT_INFRA
    except BrokenPipeError:  # `cast status | head` — не повод показывать трейсбек (§6)
        with contextlib.suppress(OSError):
            sys.stdout.close()
        return EXIT_OK


def _cmd_configure(args: Args) -> int:
    """``cast --tv <ip>`` — единственная настройка (§5).

    Отдельное значение ``mock`` включает headless-приёмник: так стенд принимается без
    телевизора (§7.5), и адрес ТВ в конфиге при этом отсутствует физически (§9).
    """
    config = load_config()
    config.tv = args.tv
    config.receiver = "mock" if args.tv == "mock" else "chromecast"
    save_config(config)
    note = " (headless-приёмник, каста наружу нет)" if args.tv == "mock" else ""
    print(f"ТВ: {config.tv}{note}")
    return EXIT_OK


def _cmd_stop() -> int:
    """``cast stop`` — снять каст и зафиксировать позицию (§2.5). Позицию пишет сам
    юнит: ``systemctl stop`` шлёт ему SIGTERM и ждёт, сторож на выходе дописывает state.
    """
    played = unit_active()
    key = unit_key()  # спрашиваем, пока юнит жив: у мёртвого описания уже не узнать
    stop_play_unit()
    found = _shown(State.load(), key)
    if not played or found is None:
        print("ничего не играет")
        return EXIT_OK
    _, entry = found
    print(f"остановлено: «{entry.title}» на {_hms(entry.pos)} / {_hms(entry.dur)}")
    return EXIT_OK


def _shown(state: State, key: str) -> tuple[str, Entry] | None:
    """Запись играющего показа: ключ берём из ``--description`` юнита, а не «самую свежую».
    Рядом мог писать другой ход — тогда свежайшая запись не та, что играет (§2.5).
    """
    entry = state.get(key) if key else None
    return (key, entry) if entry is not None else state.latest()


def _cmd_status() -> int:
    """``cast status`` — что играет, позиция/длительность, источник (§2.5). Живой юнит —
    источник правды о факте показа, позиция — из state, куда её кладёт сторож.
    """
    config = load_config()
    playing = unit_active()
    found = _shown(State.load(), unit_key() if playing else "")
    if not playing or found is None:
        print("ничего не играет")
        if found is not None and found[1].resumable:
            print(f"последнее: «{found[1].title}» на {_hms(found[1].pos)} / {_hms(found[1].dur)}")
        return EXIT_OK
    key, entry = found
    what = f"«{entry.title}»" + (f" {entry.label}" if entry.label else "")
    # Разрешение — подтверждённое ffprobe у играющего файла, а не заявка имени (§1 v1).
    what += f" · {entry.quality}" if entry.quality else ""
    print(f"играю {what} — {_hms(entry.pos)} / {_hms(entry.dur)}")
    where = "адрес раздачи не определён"
    with contextlib.suppress(TorrcastError):  # адреса нет — статус показа это не отменяет
        where = hls_base(config)
    print(
        f"   {key} · файл #{entry.file_idx} · дорожка {entry.audio + 1} · "
        f"раздача {where}, приёмник {config.receiver}"
    )
    return EXIT_OK


def _cmd_releases(args: Args) -> int:
    """``cast releases <запрос>`` — отладочная ручка §2 SPEC-v2: старая таблица и выход.

    На счастливом пути таблицы нет вовсе: релиз выбирается сам. Но посмотреть, из чего
    он выбирал, иногда надо — и тогда рядом лежит ``cast <запрос> --release N``.
    """
    config = load_config()
    inner = Args(query=list(args.query[1:]))
    if not inner.query:
        raise NotFoundError("что искать? cast releases <запрос>")
    with Progress() as progress:
        plans = _search(config, inner, progress)
    for plan in plans:
        print()
        print(f"{_named(plan.picture)} — раздач {len(plan.ranked)}")
        print(render_table(plan.ranked, plan.runtime, plan.warn_mbit, recode_at=plan.recode_at))
    print()
    print("играть конкретный: cast <запрос> --release N [--file N]")
    return EXIT_OK


def _cmd_voices(args: Args) -> int:
    """``cast voices <запрос>`` — какие озвучки есть у релиза, который поедет на ТВ.

    Отладочная ручка того же рода, что ``cast releases``: на счастливом пути озвучка
    выбирается сама (правка владельца 06-08 к §2 SPEC-v2), а посмотреть, из чего она
    выбрана, — сюда. Играть конкретную: ``cast <запрос> --voice N``.

    Показ отсюда не начинается и состояние не пишется; прогретые раздачи убираются из
    TorrServer, как и на всяком пути мимо показа (:meth:`_Bench.drop_all`).
    """
    config = load_config()
    inner = Args(query=list(args.query[1:]), release=args.release, file=args.file)
    if not inner.query:
        raise NotFoundError("что искать? cast voices <запрос>")
    with Progress() as progress:
        plans = _search(config, inner, progress)
        bench = _Bench(TorrServer(config.torrserver_url), choose=_file_picker(inner))
        try:
            plan = _pick_plan(plans)
            prep = bench.resolve(plan, inner, progress)
        finally:
            bench.drop_all()
    media = prep.found
    remembered = _remembered(State.load(), plan.picture.key, None)
    print()
    print(f"{_named(plan.picture)} — релиз №{prep.number}: {_cut(prep.release.title, 60)}")
    print(voices_table(media, media.default_track(), remembered))
    print()
    print("играть конкретную: cast <запрос> --voice N   (выбор запомнится на эту картину)")
    return EXIT_OK


def _cmd_doctor() -> int:
    """``cast doctor`` — самопроверка окружения по-русски (§3 SPEC-v2).

    Один вызов отвечает на все вопросы, которые иначе задаются владельцу: терминал и
    локаль (кириллица в вопросах), Prowlarr и TorrServer (есть чем искать и чем
    раздавать), адрес ТВ и его порт 8009 (есть кому играть), ffmpeg с ``readrate``.
    """
    from torrcast.doctor import checkup

    bad = 0
    for line, ok in checkup(load_config()):
        print(line)
        bad += 0 if ok else 1
    print()
    print("всё в порядке" if not bad else f"проблем: {bad} — смотри строки «плохо» выше")
    return EXIT_OK if not bad else EXIT_INFRA


def _cmd_worker(key: str) -> int:
    """Показ внутри transient-юнита (§3): своей раздачей, своей упаковкой и своим сторожем.

    Руками не зовётся — это ``ExecStart`` юнита ``torrcast-play``. Всё, что нужно знать о
    показе, лежит в записи состояния: magnet, файл, дорожка и позиция (§4).

    Сериал юнит доигрывает сам (§2.4): серия дошла до порога 95 % — сторож записал в
    состояние следующую, и цикл берёт её же раздачу и следующий файл, не спрашивая CLI.
    Серия была последней — состояние отмечает конец, цикл выходит, юнит гаснет чисто.

    ⚠️ **Приёмник один на весь юнит, а не на серию.** Соединение с ТВ живёт здесь и
    достаётся каждой серии готовым. Иначе получалось два сендера сразу: на стыке серий
    приложение приёмника намеренно не закрывается (:func:`_handover`), поэтому и сокет
    прошлой серии оставался жив, а следующая поднимала себе новый. Для приёмника оба —
    один и тот же ``sender-0`` (докстринг :class:`torrcast.cast.ChromecastReceiver`), и он
    отвечает новому пустым статусом. Замер на живом Q70D 06-08-2026, стык s1e5→s1e6: два
    соединения в ``ss``, «LOAD не взяли (IDLE/ERROR)», «приёмник залип — закрываю
    приложение и соединение», экран пустой **15.3 с**.
    """
    mark("процесс показа")
    config = load_config()
    # SIGTERM от `cast stop` обязан пройти через finally: иначе позиция не запишется.
    signal.signal(signal.SIGTERM, _on_term)
    torrserver = TorrServer(config.torrserver_url)
    receiver = make_receiver(
        config.receiver, config.tv or "", config.hls_cert if config.transport == "https" else ""
    )
    magnet, torrent_hash = "", ""
    while True:
        entry = State.load().get(key)
        if entry is None:
            raise InfraError(f"в состоянии нет записи {key}")
        if entry.magnet != magnet:  # раздача та же — метаданные второй раз не ждём
            magnet = entry.magnet
            torrent_hash = torrserver.add(magnet)
            torrserver.wait_files(torrent_hash, timeout=WORKER_META)
        source = torrserver.stream_url(torrent_hash, entry.file_idx)
        entry = _duration(key, entry, source)
        watch = Watch(key=key, entry=entry)
        title = " ".join(filter(None, (entry.title, entry.label)))
        print(f"показ «{title}» с {_hms(entry.pos)}", flush=True)
        code = _play(config, source, entry.audio, title, _Clock(), watch, receiver=receiver)
        following = _following(key) if watch.done else None
        if following is None:
            return code
        print(f"следующая серия: {following.label}", flush=True)


def _following(key: str) -> Entry | None:
    """Серия, которую юнит доиграет следом за только что досмотренной (§2.4).

    ``None`` — показ на этом кончается: фильм, последняя серия сезона или запись, которую
    сериалом и не считали. Отсюда же знают, закрывать ли приложение приёмника: между
    сериями оно живёт дальше, а на конце показа — гаснет (см. :func:`_play`).
    """
    entry = State.load().get(key)
    if entry is None or entry.done or not entry.label:
        return None
    return entry


def _duration(key: str, entry: Entry, source: str) -> Entry:
    """Длительность серии для порога 95 % (§2.4): следующая серия своей ещё не знает —
    её длительность лежит в её же файле, и читается она из потока, как дорожки (§3).
    """
    if entry.dur > 0:
        return entry
    entry.dur = probe(source, timeout=WORKER_DUR).duration
    state = State.load()
    state.put(key, entry)
    state.save()
    return entry


class _Stopped(KeyboardInterrupt):
    """``cast stop``: SIGTERM пришёл, показ окончен штатно — это не авария.

    Наследуемся от ``KeyboardInterrupt`` намеренно: раскрутка обязана пройти ровно так
    же, как проходила, — через ``finally`` в :func:`_play`, где пишется позиция, гаснет
    упаковка и снимается каст. Меняется только вывеска на выходе: ``cast stop`` — это
    успех, и юнит обязан умереть кодом 0, иначе systemd помечает его ``failed``, а
    владелец видит красное `● torrcast-play … failed` после каждой штатной остановки.
    """


def _on_term(_signal: int, _frame: object) -> None:
    raise _Stopped


@dataclass(slots=True)
class Watch:
    """Сторож: раз в :data:`WATCH_SECONDS` кладёт позицию приёмника в state (§3, §4).

    Позиция приходит абсолютной: манифест описывает весь фильм, а ``-copyts`` оставляет
    в сегментах исходные метки времени, поэтому приёмник считает время от начала фильма
    независимо от того, с какого места идёт упаковка (§2.1 SPEC-v2). Пересчитывать
    смещение показу больше не нужно — раньше это была отдельная строчка возможной лжи.
    Порог 95 % — «досмотрено» (§2.4): фильму сброс с пометкой, сериалу следующая серия.
    """

    key: str
    entry: Entry
    every: float = WATCH_SECONDS
    done: bool = False
    last: float = field(default_factory=time.monotonic)

    def see(self, pos: float) -> None:
        """Позиция от приёмника; на диск — не чаще раза в ``every`` секунд. Порог 95 %
        записывается сразу: на нём держится стык серий, ждать тика ещё 10 с незачем.
        """
        if pos <= 0:  # приёмник ещё не начал считать — нулём позицию не затираем
            return
        self.entry.pos = pos
        if self.entry.watched or time.monotonic() - self.last >= self.every:
            self.flush()

    def flush(self) -> None:
        """Записать состояние атомарно (tmp + rename в :mod:`torrcast.state`)."""
        if self.done:  # досмотренную запись повторными тиками не портим
            return
        self.last = time.monotonic()
        state = State.load()  # перечитываем: рядом мог писать другой ход
        self.done = self.entry.watched
        state.put(self.key, self.entry.advance() if self.done else self.entry)
        state.save()
        if self.done:
            what = f" {self.entry.label}" if self.entry.label else ""
            print(f"досмотрено{what}: {_hms(self.entry.pos)} из {_hms(self.entry.dur)}", flush=True)


@dataclass(slots=True)
class _Clock:
    """Фазы старта: §3.1 обещает холодные 15–30 с, и цифры должны быть видны глазами."""

    start: float = field(default_factory=time.monotonic)
    last: float = field(default_factory=time.monotonic)

    def lap(self) -> str:
        now = time.monotonic()
        gap, self.last = now - self.last, now
        return f"{gap:.1f} с"

    @property
    def total(self) -> float:
        return time.monotonic() - self.start


def _cmd_play(args: Args) -> int:
    """Счастливый путь §2 SPEC-v2: запрос → «какой фильм?» → «какая озвучка?» → показ.

    Релиз и файл выбираются сами, таблиц и списков файлов на этом пути нет. Пока человек
    отвечает на вопрос про франшизу, топ-3 кандидата уже греются в TorrServer и читаются
    ffprobe (§4): к моменту ответа критический путь чаще всего пуст.

    ``--new`` здесь ничего не стирает: сохранённая позиция уходит в расход только тогда,
    когда показ уже точно начинается (:func:`_forget_progress`). Почему так — там же.
    """
    mark("команда")
    clock = _Clock()
    config = load_config()
    state = State.load()
    found_entry = state.find(args.title_query)
    # --new: прежний прогресс не продолжаем и выбираем заново (§4), но запись пока цела.
    stale = found_entry[0] if found_entry is not None and args.new else None
    if found_entry is not None and not args.new:
        code = _continue(config, *found_entry, args=args, clock=clock)
        if code is not None:
            return code

    with Progress() as progress:
        plans = _search(config, args, progress)
        torrserver = TorrServer(config.torrserver_url)
        bench = _Bench(torrserver, choose=_file_picker(args))
        # Прогрев под меню (§4 SPEC-v2): пока идёт вопрос, раздачи уже качают метаданные.
        for plan in warm_order(plans)[:PREWARM]:
            bench.start(plan, plan.first)
        try:
            plan = _pick_plan(plans)
            prep = bench.resolve(plan, args, progress)
        except BaseException:  # Ctrl-C, «картин много, а терминала нет», «годного нет»
            bench.drop_all()  # прогретое без показа — мусор в рое и кэш в чужой RAM
            raise
        bench.keep_only(prep)  # прогрев греет лишнее — до показа лишнее убираем

    release, video, media = prep.release, prep.want, prep.found
    audio, voice = pick_voice(media, args, _remembered(state, plan.picture.key, found_entry))
    mark("ответы")  # ноль секундомера §7.1: Enter после последнего вопроса
    label = media.tracks[audio].label if audio < len(media.tracks) else "—"
    series = plan.series
    what = f"«{plan.picture.title}»" + (
        f" {series.want}" if series else f" ({plan.picture.year or '?'})"
    )
    about = f"{what} · {quality_text(release, media)} · {label}"
    # Настоящий битрейт: размер файла серии/фильма на его же длительность, а не оценка.
    peak = bitrate_mbit(video.size, media.duration or plan.runtime)
    if peak > config.bitrate_warn_mbit:
        print(
            f"внимание: ~{peak:.0f} Мбит/с — тяжёлые куски перекодирую на ходу"
            if config.recode
            else f"внимание: ~{peak:.0f} Мбит/с — ресивер на таком битрейте может встать"
        )
    if args.pinned:  # отладочный путь: тут внутренности показывать и надо
        print(f"файл: {video.base} · {_gb(video.size)} · {_hms(media.duration)} · {media.video}")
    if args.dry:
        print(f"(--dry) {about} — каста нет")
        return EXIT_OK
    entry = Entry(
        title=plan.picture.title,
        magnet=release.magnet,
        kind="tv" if plan.picture.kind == "tv" else "movie",
        file_idx=video.index,
        audio=audio,
        voice=voice,
        dur=media.duration,
        # То, что уехало на ТВ: `cast status` покажет факт, а не заявку имени (§1 v1).
        quality=media.quality if media.height else "",
        query=slugify(args.title_query),
        season=series.want.season if series else None,
        episode=series.want.episode if series else None,
        episodes=series.table if series else [],
    )
    if stale is not None:  # точка невозврата пройдена — вот теперь --new вправе забывать
        _forget_progress(stale)
    return _launch(config, plan.picture.key, entry, about, clock)


def _forget_progress(key: str) -> None:
    """Забыть прежний прогресс по ``--new`` — в момент, когда показ уже точно начинается.

    Раньше запись стиралась первым же действием команды, до единого вопроса. Любой обрыв
    после этого — «ничего не разобралось», Ctrl-C, упавший ffprobe, а на прогоне без
    терминала ещё и выбор вслепую — оставлял владельца без сохранённого места, и взять
    его было неоткуда: state уже перезаписан (ровно так и потерялась запись фильма).

    Раннее стирание при этом ничего не давало: свежую запись с нулевой позицией всё равно
    кладёт :func:`_launch`. То есть у него была одна цена и ни одной пользы.
    """
    state = State.load()  # перечитываем: рядом мог писать другой ход
    state.drop(key)
    state.save()


def _search(config: Config, args: Args, progress: Progress) -> list[_Plan]:
    """Поиск и разбор выдачи: запрос → картины франшизы, каждая со своим пулом релизов."""
    from torrcast.parse import cluster, pick_franchise

    if not config.prowlarr_apikey:  # без Prowlarr искать нечем — это инфра-ошибка
        raise InfraError("не настроен Prowlarr: apikey пуст, перезапусти ./install.sh")
    query = args.title_query
    name, _ = split_franchise_index(query)
    progress.phase(f"поиск «{name}»")
    raw = Prowlarr(config.prowlarr_url, config.prowlarr_apikey).search(name)
    mark("поиск", найдено=len(raw))
    pictures = cluster(to_releases(raw))
    if not pictures:
        raise NotFoundError(f"по запросу «{name}» ничего не разобралось")
    # Номер в запросе — позиция во франшизе, а не в общей выдаче (§2.2).
    found = pick_franchise(query, pictures)
    if not found:
        raise NotFoundError(f"«{query}» — такой картины во франшизе нет")
    progress.phase("")
    plans = [plan for plan in (_plan_for(p, args, config) for p in found) if plan.ranked]
    if not plans:  # картина есть, а раздач нужного сезона в ней нет (§2.4)
        want = args.episode or Episode(1, 1)
        raise NotFoundError(f"«{found[0].title}»: раздач с сезоном {want.season} нет")
    return plans


def _plan_for(picture: Picture, args: Args, config: Config) -> _Plan:
    """План по одной картине: пул релизов в порядке отбора и цель для сериала (§2.4)."""
    from torrcast.stream import RUNTIME_GUESS

    series = _Series(want=args.episode or Episode(1, 1)) if picture.kind == "tv" else None
    runtime = RUNTIME_GUESS.get(picture.kind, 7200.0)
    pool = picture.releases
    if series is not None:
        pool = [r for r in pool if r.covers(series.want.season)]
    # §6.2: потолок отбора перестал быть потолком декодера. Тяжёлые куски перекодируются
    # (:mod:`torrcast.recode`), поэтому честный тяжёлый 1080p теперь берётся, а отбраковывает
    # только то, что перекодированием не спасти, — ``bitrate_hard_mbit``. Перекодирование
    # выключено — потолком снова становится прежний ``bitrate_warn_mbit``.
    ceiling = config.bitrate_hard_mbit if config.recode else config.bitrate_warn_mbit
    ranked = rank_releases(pool, runtime, ceiling)
    return _Plan(
        picture=picture,
        ranked=ranked,
        runtime=runtime,
        warn_mbit=ceiling,
        series=series,
        recode_at=config.recode_at_mbit if config.recode else 0.0,
    )


@dataclass(slots=True)
class _Plan:
    """Что покажем по одной картине: пул релизов и, для сериала, нужная серия.

    План строится на **все** картины франшизы ещё до вопроса — иначе прогрев под меню
    невозможен: греть надо то, что человек, скорее всего, выберет (§4 SPEC-v2).
    """

    picture: Picture
    ranked: list[Release]
    runtime: float
    #: Потолок ОТБРАКОВКИ, Мбит/с: выше него релиз не берём вовсе (см. :func:`_plan_for`).
    warn_mbit: float
    series: _Series | None = None
    #: Порог ПЕРЕКОДИРОВАНИЯ, Мбит/с: выше него куски перекодируются, а релиз годен.
    #: Ноль — перекодирование выключено, и тогда отбраковка и порог это одно число.
    recode_at: float = 0.0

    @property
    def first(self) -> int:
        """Номер релиза, который берём по умолчанию: он же верх :func:`rank_releases`."""
        return 1

    def candidates(self, args: Args) -> list[int]:
        """Очередь релизов: сначала дефолт, потом годные запасные (§2 SPEC-v2)."""
        if args.release is not None:
            if not 1 <= args.release <= len(self.ranked):
                raise NotFoundError(f"релизов {len(self.ranked)}, номера {args.release} нет")
            return [args.release]
        queue = [self.first]
        queue += [
            n
            for n, r in enumerate(self.ranked, start=1)
            if n != self.first and is_candidate(r, self.runtime, self.warn_mbit)
        ]
        return queue[:MAX_TRIES]


@dataclass(slots=True)
class _Series:
    """Серии выбранной раздачи (§2.4): файлы → ``sNeM``, нужный файл и кэш для состояния.

    Пак это или один сезон — решают ФАЙЛЫ, а не имя раздачи: сколько сезонов нашлось в
    путях, столько и будет в списке, и прыжок `s2e5` внутри пака обойдётся без поиска.
    """

    want: Episode
    files: list[EpisodeFile] = field(default_factory=list)

    def choose(self, release: Release, files: list[TorrFile]) -> TorrFile:
        """Файл нужной серии; такой серии в раздаче нет — честная строка со списком (§1)."""
        self.files = map_episodes(files, release.season)
        found = next((f for f in self.files if f.at == self.want), None)
        if found is None:
            raise NotFoundError(
                f"серии {self.want} в этой раздаче нет ({self.summary()}) — "
                "возьми другую раздачу: cast <запрос> --release N"
            )
        return next(f for f in files if f.index == found.index)

    @property
    def table(self) -> list[list[int]]:
        """Список серий для состояния (§4): по нему идут автопереход и прыжки."""
        return [[f.season, f.episode, f.index] for f in self.files]

    def summary(self) -> str:
        """«серий 10: s1e1…s1e10», для пака — ещё и диапазон сезонов."""
        if not self.files:
            return "серий не нашлось"
        seasons = {f.season for f in self.files}
        span = f"сезоны {min(seasons)}–{max(seasons)} · " if len(seasons) > 1 else ""
        return f"{span}серий {len(self.files)}: {self.files[0].at}…{self.files[-1].at}"


def _continue(config: Config, key: str, entry: Entry, args: Args, clock: _Clock) -> int | None:
    """Продолжение по сохранённому выбору (§2.3, §2.4). ``None`` — состоянием не обойтись,
    дальше идёт обычный путь с поиском и меню.

    Сериал вопросов не задаёт вовсе: релиз, дорожка и список серий уже выбраны, а
    какую серию и с какого места играть — записано. Фильм спрашивает ровно одно (§2.3).
    """
    if not entry.serial:  # фильм (в том числе ошибочно записанный сериалом) — один вопрос
        if not entry.resumable:
            return None  # продолжать нечего — озвучку выберет обычный путь, по дорожкам
        return _resume(config, key, _voiced(config, entry, args), clock=clock, dry=args.dry)
    entry = _voiced(config, entry, args)
    if args.episode is not None:  # `cast киберпанк s2e5` — прыжок по кэшу раздачи
        jumped = entry.jump(args.episode.season, args.episode.episode)
        if jumped is None:
            return None  # серии в этой раздаче нет — честно идём искать релиз сезона
        return _launch(config, key, jumped, _about(jumped), clock, args.dry)
    if entry.done:  # конец раздачи: сама собой следующая серия не появится
        print(f"«{entry.title}» — {entry.label} была последней в раздаче")
        if ask_line("Смотреть сначала? [Да/нет]")[:1] in {"н", "n"}:
            return EXIT_OK
        first = entry.episodes[0]
        entry = entry.jump(first[0], first[1]) or entry
    return _launch(config, key, entry, _about(entry), clock, args.dry)


def _remembered(state: State, key: str, found: tuple[str, Entry] | None) -> str:
    """Озвучка, которую владелец выбирал для этой картины (§2 SPEC-v2, правка 06-08).

    Смотрим по каноническому ключу картины — под ним показ и пишет запись. Запись,
    найденную по тексту запроса (:meth:`State.find`), берём запасным вариантом: у
    одной картины в состоянии могут лежать записи разных запросов («moana» и «моана»),
    и память озвучки не должна зависеть от того, как её позвали в прошлый раз.
    """
    entry = state.get(key) or (found[1] if found is not None else None)
    return entry.voice if entry is not None else ""


def _voiced(config: Config, entry: Entry, args: Args) -> Entry:
    """Запись с учётом ``--voice``; без флага — она же, не тронутая и без похода в рой.

    Флага нет — не читаем ничего: этот путь тем и хорош, что обходится состоянием.
    ⚠️ Звать только тогда, когда запись действительно пойдёт в показ. Живая грабля
    06-08: вызов до проверки «есть ли что продолжать» лез в TorrServer за раздачей,
    которую никто играть не собирался, и падал на её магните.
    """
    return entry if args.voice is None else _revoice(config, entry, args)


def _revoice(config: Config, entry: Entry, args: Args) -> Entry:
    """``--voice`` поверх сохранённого выбора: перечитать дорожки раздачи и взять нужную.

    Нужно ровно для сериала и продолжения: там показ идёт по записи состояния и потока
    никто не читает — ни номеров дорожек, ни подписей взять неоткуда. Платим за это
    метаданными раздачи и одним ffprobe (секунды, с живым прогрессом), и платим только
    когда флаг назван: счастливый путь этой цены не видит.

    Состояние отсюда не пишется: выбор уезжает в запись показа (:func:`_launch`) вместе
    с позицией и серией. Так у ``--dry`` не остаётся следов, а память не переписывается
    показом, который не начался.
    """
    torrserver = TorrServer(config.torrserver_url)
    with Progress() as progress:
        progress.phase("дорожки")
        torrent_hash = torrserver.add(entry.magnet)
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
    """Подготовка одного релиза целиком в фоне: раздача, файл, дорожки (§4 SPEC-v2).

    Это и есть обещанный, но так и не написанный прогрев под меню. Фазы идут своим
    ходом в отдельном потоке, а показ спрашивает только результат — поэтому 17 секунд
    ffprobe на «Моане 2» уходят из критического пути в паузу между вопросами.

    Каждая фаза имеет **бюджет**: не уложилась — это не «зависло насмерть» без единого
    слова (дефект №1 владельца), а :attr:`error` и следующий релиз в очереди.
    """

    number: int
    release: Release
    torrent_hash: str = ""
    #: Прогрев оказался ненужным: показ ушёл на другую картину или другой релиз. Такая
    #: раздача убирается из TorrServer сразу — иначе два лишних торрента тянули бы кэш
    #: и полосу у самого показа.
    dropped: bool = False
    video: TorrFile | None = None
    media: Media | None = None
    error: str = ""
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


class _Bench:
    """Прогрев релизов: несколько раздач готовятся разом, показ берёт первую годную.

    Держит по потоку на релиз и умеет ждать нужный с живым прогрессом. Любая осечка
    (нет пиров, не читается поток, оказался HEVC) стоит одной строки и перехода к
    следующему кандидату — молчаливых подмен и молчаливых зависаний не бывает (§1 v1,
    §1 SPEC-v2).
    """

    def __init__(
        self,
        torrserver: TorrServer,
        choose: Callable[[_Plan, Release, list[TorrFile]], TorrFile] | None = None,
        meta_budget: float = META_BUDGET,
        probe_budget: float = PROBE_BUDGET,
    ) -> None:
        self.torrserver = torrserver
        self.choose = choose or _default_file
        self.meta_budget = meta_budget
        self.probe_budget = probe_budget
        self.preps: dict[tuple[str, int], _Prep] = {}

    def start(self, plan: _Plan, number: int) -> _Prep:
        """Начать (или вернуть уже начатую) подготовку релиза ``number`` этого плана."""
        key = (plan.picture.key, number)
        found = self.preps.get(key)
        if found is not None:
            return found
        prep = _Prep(number=number, release=plan.ranked[number - 1])
        self.preps[key] = prep
        threading.Thread(target=self._work, args=(plan, prep), daemon=True).start()
        return prep

    def resolve(self, plan: _Plan, args: Args, progress: Progress) -> _Prep:
        """Годный релиз плана: ждём подготовку с прогрессом, негодный — следующий (§2)."""
        queue = plan.candidates(args)
        tried: list[str] = []
        for attempt, number in enumerate(queue, start=1):
            prep = self.start(plan, number)
            following = queue[attempt] if attempt < len(queue) else None
            if following is not None:  # запасной греется, пока ждём этот
                self.start(plan, following)
            self._wait(prep, progress)
            trouble = self._trouble(prep, pinned=args.pinned, warn_mbit=plan.warn_mbit)
            if not trouble:
                progress.phase("")
                prep = self._honest(plan, prep, queue, args, progress)
                if warning := prep.found.video_warning:  # названный релиз играем, но не молча
                    print(warning)
                return prep
            tried.append(f"№{number} — {trouble}")
            self._forget(prep)
            progress.phase("")
            tail = f" — беру №{following}" if following else ""
            print(f"релиз №{number} не годится ({trouble}){tail}")
        raise NotFoundError(
            f"годного релиза нет ({'; '.join(tried)}): выбери руками — "
            "cast releases <запрос>, потом cast <запрос> --release N"
        )

    def _wait(self, prep: _Prep, progress: Progress) -> None:
        """Дождаться подготовки, показывая фазу и бегущее время (§4 SPEC-v2)."""
        deadline = prep.started + self.meta_budget + self.probe_budget + 5.0
        while not prep.ready.wait(0.2):
            progress.phase(prep.phase)
            if time.monotonic() > deadline:  # поток сам не уложился — не ждём вечно
                prep.error = prep.error or f"фаза «{prep.phase}» не уложилась в бюджет"
                return

    def _peek(self, prep: _Prep, progress: Progress, deadline: float, phase: str) -> bool:
        """Заглянуть в подготовку с коротким сроком: успела — ``True``, нет — ``False``.

        Отличие от :meth:`_wait` не в сроке, а в последствиях: этот срок наш, а не
        релиза, и просроченному прогреву :attr:`_Prep.error` не ставится. Иначе
        подглядывание за соседом молча делало бы его негодным.
        """
        while not prep.ready.wait(0.2):
            progress.phase(phase)
            if time.monotonic() > deadline:
                return False
        return True

    def _honest(
        self, plan: _Plan, chosen: _Prep, queue: list[int], args: Args, progress: Progress
    ) -> _Prep:
        """Подтверждённое разрешение против обещанного: 574p вместо 1080p — не мелочь.

        Верх отбора — самый обсиженный годный кандидат, и это правило остаётся (§2.1 v1).
        Но обсиженность считается **среди честных**: если ffprobe уже прочитан и говорит,
        что внутри верха не HD, а рядом в очереди стоит живой релиз, который обещает
        1080p, — стоит спросить у ffprobe и его. Живой случай, ради которого это
        написано: «Моана 2», верх ``WEB-DL-AVC`` 3.14 ГБ / 140 сидов оказался 1150×574,
        а вторым лежит настоящий 1080p 13.3 ГБ со 121 сидом.

        Платим за проверку немного: запасной греется с той же секунды, что и верх
        (:meth:`resolve` поднимает следующего сразу), поэтому ждём не прогрев, а разницу
        двух ffprobe, и не дольше :data:`HONEST_BUDGET`.

        Молчаливых подмен нет в обе стороны: и подмена, и отказ от неё печатают строку.
        ``--release N`` и ``--file N`` не трогаем вовсе — там человек выбрал сам.
        """
        if args.release is not None or args.pinned:
            return chosen
        short = understated(chosen.release, chosen.found)
        if not short:
            return chosen
        rest = [
            n
            for n in queue
            if n != chosen.number and promises_more(plan.ranked[n - 1], chosen.found)
        ]
        deadline = time.monotonic() + HONEST_BUDGET
        for number in rest:
            alt = self.start(plan, number)
            phase = f"№{chosen.number} {short} — смотрю №{number}"
            if not self._peek(alt, progress, deadline, phase):
                progress.phase("")
                print(f"релиз №{number} не успел ответить — играю №{chosen.number} ({short})")
                return chosen
            progress.phase("")
            why = self._trouble(alt, pinned=False, warn_mbit=plan.warn_mbit)
            if why:
                print(f"релиз №{number} не годится ({why})")
                continue
            if not honest_shot(alt.release, alt.found) or alt.found.frame <= chosen.found.frame:
                print(f"релиз №{number} не лучше ({quality_text(alt.release, alt.found)})")
                continue
            print(
                f"релиз №{chosen.number} {short} — беру №{number} (настоящий {alt.found.quality})"
            )
            self._forget(chosen)  # верх больше не нужен: полосу роя доедать ему незачем
            return alt
        print(f"релиз №{chosen.number} {short} — честнее рядом нет, играю его")
        return chosen

    def _trouble(self, prep: _Prep, pinned: bool, warn_mbit: float = 0.0) -> str:
        """Почему релиз не годится; пусто — годится. Названный руками не подменяется.

        Битрейт здесь считается **по прочитанному файлу**, а не по размеру раздачи, и это
        разные числа: у «Моаны 2» прикидка (:func:`bitrate_of`) делит 13.3 ГБ на типовые
        два часа и даёт 14.8 Мбит/с, а внутри — фильм на 1:39:37, то есть честные
        17.8 Мбит/с, на которых Q70D встаёт в ребуфер раз в 30–60 с (§7.5 SPEC-v2).
        Прикидка потолка при выборе дефолта такой релиз пропускала и пропускать будет:
        до ffprobe длительности картины не знает никто. Поэтому потолок проверяется ещё
        раз — тем же числом, которое показ печатает владельцу.

        ⚠️ С 06-08 вечера (§6.2) ``warn_mbit`` здесь — это ``bitrate_hard_mbit``, а не
        потолок декодера: тяжёлые куски перекодируются, и «Моана 2» на 19 Мбит/с теперь
        годится. Отбраковывается только то, что перекодированием не спасти.
        """
        if prep.error:
            return prep.error
        if prep.media is None or prep.video is None:
            return "поток не прочитан"
        if not pinned and warn_mbit > 0:
            peak = bitrate_mbit(prep.video.size, prep.media.duration)
            if peak > warn_mbit:
                return f"тяжёлый, ~{peak:.0f} Мбит/с"
        codec = prep.media.video or "h264"
        return "" if pinned or codec == "h264" else codec

    def _forget(self, prep: _Prep) -> None:
        """Убрать раздачу из TorrServer: она либо не подошла, либо больше не нужна."""
        prep.dropped = True
        if prep.torrent_hash:
            self.torrserver.drop(prep.torrent_hash)

    def drop_all(self) -> None:
        """Показа не будет: всё прогретое убирается из TorrServer.

        Выходов мимо :meth:`keep_only` хватает — Ctrl-C на вопросе «Что смотрим?», запуск
        без терминала, «годного релиза нет». Раздачи при этом уже добавлены и тянут кэш в
        RAM до перезапуска TorrServer: ``save_to_db`` у них выключен, но живут они не в
        нашем процессе, и умирают не вместе с ним.
        """
        for prep in self.preps.values():
            self._forget(prep)

    def keep_only(self, chosen: _Prep) -> None:
        """Оставить в TorrServer одну раздачу — ту, которую показываем.

        Прогрев по определению греет лишнее: топ-3 картины франшизы и запасной релиз.
        Всё лишнее обязано исчезнуть до старта показа, иначе оно доедает и кэш в RAM,
        и полосу роя, а показ идёт ровно на них (§6 SPEC-v2: tmpfs не растёт без предела).
        """
        for prep in self.preps.values():
            if prep is not chosen:
                self._forget(prep)

    def _work(self, plan: _Plan, prep: _Prep) -> None:
        """Фоновая подготовка: раздача в TorrServer, метаданные по DHT, ffprobe."""
        try:
            prep.phase = "метаданные (DHT)"
            prep.torrent_hash = self.torrserver.add(prep.release.magnet)
            files = self.torrserver.wait_files(prep.torrent_hash, timeout=self.meta_budget)
            prep.meta = time.monotonic() - prep.started
            mark("метаданные", релиз=prep.number, картина=plan.picture.key)
            prep.video = self.choose(plan, prep.release, files)
            prep.phase = "дорожки"
            began = time.monotonic()
            source = self.torrserver.stream_url(prep.torrent_hash, prep.want.index)
            # Всё, что показ прочитает из роя первым, читается здесь и сейчас: карта
            # опорных кадров (без неё нет сетки) и начало файла (его читает ffmpeg). Это
            # самая ранняя секунда, когда известен файл, — то есть параллельно и ffprobe,
            # и вопросам человека (§4 SPEC-v2). Показ потом либо берёт готовое, либо
            # дожидается этого же чтения, а не начинает своё вторым потоком.
            warm_file(source, alive=lambda: not prep.dropped, name=prep.want.name)
            prep.media = probe(source, timeout=self.probe_budget)
            prep.read = time.monotonic() - began
            mark("ffprobe", релиз=prep.number, картина=plan.picture.key)
            prep.phase = "готово"
        except TorrcastError as exc:
            prep.error = str(exc)
            prep.phase = "сбой"
        finally:
            prep.ready.set()
            if prep.dropped:  # пока грелись, показ ушёл к другому релизу
                self._forget(prep)


def _default_file(plan: _Plan, release: Release, files: list[TorrFile]) -> TorrFile:
    """Фильму — самый крупный видеофайл, сериалу — файл нужной серии (§2.4)."""
    return plan.series.choose(release, files) if plan.series else pick_video_file(files)


def _file_picker(args: Args) -> Callable[[_Plan, Release, list[TorrFile]], TorrFile]:
    """``--file N`` — отладочная ручка §2 SPEC-v2: взять N-й видеофайл раздачи."""
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
    человек читает вопрос, и она тут и тратится (§7.2 SPEC-v2).

    Смещение позиции в байтах берётся из карты опорных кадров
    (:meth:`torrcast.stream.FilmKeys.byte_at`) — той же самой, по которой строится сетка.
    Пропорция «доля фильма от размера файла» сюда не годится: битрейт по фильму гуляет
    вдвое, и промах в проценте — это десятки мегабайт, то есть прогрев не того места.
    """

    torrserver: TorrServer
    entry: Entry
    source: str = ""
    cancelled: bool = False

    def start(self) -> None:
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        with contextlib.suppress(TorrcastError):
            torrent_hash = self.torrserver.add(self.entry.magnet)
            files = self.torrserver.wait_files(torrent_hash)
            self.source = self.torrserver.stream_url(torrent_hash, self.entry.file_idx)
            # Имя файла — подсказка о контейнере для грелки головы: карта, снятая прошлой
            # версией, лежит в кэше без него (:func:`torrcast.stream.container_of`).
            name = next((f.name for f in files if f.index == self.entry.file_idx), "")
            warm_file(self.source, at=self.entry.pos, alive=lambda: not self.cancelled, name=name)

    def enough(self) -> None:
        """Ответ получен — прогрев прекращается, дальше те же байты читает сам показ.

        ⚠️ Это не мелочь и не гигиена, а замер. Прогрев, доигрывающий после Enter'а, —
        это **второй** читатель того же места через TorrServer, и он отбирает у показа
        ровно то, ради чего затевался: на стенде 06-08-2026 пробный прогон вырос с 0.56
        до 1.92 с, а готовность LOAD — с 3.5 до 4.8 с. Смысл прогрева весь в секундах
        ДО ответа; после ответа лучший потребитель полосы — ffmpeg.

        «Сначала» отменяет прогрев по той же причине, только резче: середина фильма
        больше не нужна вовсе.
        """
        self.cancelled = True


def _resume(config: Config, key: str, entry: Entry, clock: _Clock, dry: bool = False) -> int:
    """Возобновление §2.3: один вопрос и сразу показ. Релиз, файл и дорожка берутся из
    состояния — ни поиска, ни меню, поэтому старт укладывается в 5–15 с (§3.1).

    Пока задаётся вопрос, раздача уже поднята в TorrServer, а рой прогрет по месту
    сохранённой позиции (:class:`_Resume`): к Enter'у критический путь чаще всего пуст.
    """
    warm = _Resume(TorrServer(config.torrserver_url), entry)
    warm.start()
    question = f"«{entry.title}» остановились на {_hms(entry.pos)}. Продолжить? [Да/сначала]"
    answer = ask_line(question)
    warm.enough()
    if answer[:1] in {"с", "s", "н", "n"}:  # «сначала» / «с начала» / «нет»
        entry.pos = 0.0
    mark("ответы")  # ноль секундомера §7.2: Enter после последнего вопроса
    return _launch(config, key, entry, _about(entry), clock, dry)


def _launch(
    config: Config, key: str, entry: Entry, about: str, clock: _Clock, dry: bool = False
) -> int:
    """Показ уезжает в transient-юнит: ``cast`` завершился — показ продолжается (§3)."""
    if dry:
        print(f"(--dry) {about} — каста нет")
        return EXIT_OK
    # Сначала гасим прошлый показ и только потом пишем свою запись: умирающий юнит по
    # SIGTERM дописывает СВОЮ позицию, и записанный раньше прыжок на s1e5 он бы затёр.
    stop_play_unit()
    state = State.load()
    state.put(key, entry)
    state.save()
    forget_playing(Path(config.hls_dir))  # флажок прошлого показа нам не доказательство
    start_play_unit(key)
    mark("юнит")
    with Progress() as progress:
        _await_playing(config, progress)
    print(f"играю {about} — на ТВ   (старт {clock.total:.0f} с)")
    return EXIT_OK


def _await_playing(config: Config, progress: Progress, timeout: float = START_BUDGET) -> None:
    """Дождаться **картинки на экране**, а не «упаковка пошла» (§4 SPEC-v2).

    Две разные вещи, которые в v1 были одной: первый сегмент в tmpfs — это упаковка, а
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
    raise InfraError(f"показ не начался за {timeout:.0f} с — {unit_why()}")


def _recoder(source: str, audio: int, grid: Grid, spare: Path, config: Config) -> Recoder | None:
    """Кодировщик тяжёлых кусков или ``None``, если он не нужен и не может помочь (§6.2).

    Профиль тяжести считается из уже снятой карты опорных кадров: байты и секунды каждого
    сегмента известны до упаковки, и это ноль запросов к рою. Отказ бывает честный —
    выключено настройкой, сетка не по кадрам (тогда границы не совпадут с картой), карта
    снята прошлой версией и смещений не несёт, — и о нём говорится вслух.
    """
    from torrcast.recode import Encode, Recoder, Weights
    from torrcast.stream import film_keys

    if not config.recode:
        return None
    if not grid.on_keys:
        print("сетка не по опорным кадрам — тяжёлые куски перекодировать не берусь", flush=True)
        return None
    try:
        keys = film_keys(source)
    except InfraError as exc:
        print(f"профиль тяжести не снят ({why(exc)}) — играю как есть", flush=True)
        return None
    weights = Weights.of(keys, grid)
    if weights is None:
        print("карта без смещений — профиль тяжести не построить, играю как есть", flush=True)
        return None
    return Recoder(
        source=source,
        audio=audio,
        grid=grid,
        spare=spare,
        weights=weights,
        threshold=config.recode_at_mbit,
        encode=Encode(preset=config.recode_preset, mbit=config.recode_mbit),
        ahead=config.recode_ahead,
        cache_mb=config.recode_cache_mb,
        head_wait=config.recode_head_wait,
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
) -> int:
    """Упаковка → раздача по http на голом IP (§5 SPEC-v2) → приёмник. Своих демонов
    нет: и ffmpeg, и раздача живут ровно на время показа и гасятся вместе с ним, что бы
    ни случилось.

    Упаковка за показ перезапускается столько раз, сколько человек перемотал (§2.1
    SPEC-v2): манифест обещает приёмнику весь фильм, а :class:`Feed` пакует то место,
    которое он попросил. Раздача, приёмник и LOAD при этом одни на весь показ.
    """
    from torrcast.recode import RECODE_DIR
    from torrcast.stream import grid_for, hls_base, hls_dir

    out = hls_dir(config.hls_dir)
    start = watch.entry.pos if watch else 0.0
    length = watch.entry.dur if watch else duration
    tls = config.transport == "https"
    # Сетка сегментов снимается с самого файла и дальше не меняется: она же в манифесте,
    # она же в команде ffmpeg. Всё, что показ говорит о времени, считается по ней.
    grid = grid_for(
        source,
        length,
        config.hls_segment,
        config.hls_keyframes,
        say=lambda text: print(text, flush=True),
    )
    mark("сетка", сегментов=grid.count, покадрам=grid.on_keys)
    # §6.2: профиль тяжести всего фильма известен со старта — он считается из уже снятой
    # карты опорных кадров и не стоит ни одного запроса к рою. Тяжёлые куски кодировщик
    # начнёт перекодировать сразу, пока играет остальное.
    recoder = _recoder(source, audio, grid, out / RECODE_DIR, config)
    feed = Feed(
        source=source,
        audio=audio,
        out=out,
        grid=grid,
        readrate=config.hls_readrate,
        burst=config.hls_burst,
        keep=config.hls_keep,
        log=lambda text: print(text, flush=True),
        recoder=recoder,
    )
    server = HlsServer(
        out, config.hls_cert, config.hls_key, port=config.hls_port, tls=tls, feed=feed
    )
    # Серт приёмнику нужен только затем, чтобы проверить нашу раздачу: по http проверять
    # нечего, и mock не должен делать вид, что что-то проверил. Готовый приёмник приходит
    # с сериалом: он один на весь юнит (см. :func:`_cmd_worker`).
    if receiver is None:
        receiver = make_receiver(config.receiver, config.tv or "", config.hls_cert if tls else "")
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
        print(f"играю {about} — на ТВ   (старт {clock.total:.0f} с)", flush=True)
        _hold(receiver, feed, watch)
    finally:
        # Позиция фиксируется при любом исходе, включая SIGTERM, и делается это ПЕРВЫМ
        # делом: показ, доигранный до конца файла, отмечает «досмотрено» ровно здесь, а
        # приёмнику ниже нужно уже готовое состояние — по нему он и узнаёт, конец это
        # показа или стык серий.
        if watch is not None:
            watch.flush()
        # ⚠️ suppress(Exception), а не TorrcastError: pychromecast на полуживом соединении
        # роняет что угодно, а ffmpeg и раздача обязаны погаснуть в любом случае — иначе
        # процесс уходит, а они остаются.
        with contextlib.suppress(Exception):
            # Показ кончился — приложение приёмника закрываем, чтобы ТВ вернулся в
            # исходное состояние: иконка Default Media Receiver иначе висит до своего
            # таймаута простоя и оттягивает автовыключение (дефект владельца 05-08).
            # Исключение ровно одно — стык серий: следующая серия грузится в то же
            # приложение, и гасить его между ними значит моргать экраном на каждой.
            receiver.stop(quit_app=not _handover(watch))
        feed.stop()
        server.stop()

    report = getattr(receiver, "report", None)
    if report is None:
        return EXIT_OK
    print(report.line())
    # Серию обрывают намеренно на пороге 95 % — хвост упаковки декодеру и не отдавали.
    if not report.ok and not (watch is not None and watch.done):
        raise InfraError("приёмник не досмотрел поток — цифры выше")
    return EXIT_OK


def _handover(watch: Watch | None) -> bool:
    """Правда ли показ передают следующей серии, а не заканчивают.

    Порог 95 % уже записал в состояние следующую серию (:meth:`Watch.flush`), поэтому
    ответ лежит там же, где его читает :func:`_cmd_worker`, — двух разных мнений о конце
    показа быть не должно.
    """
    return watch is not None and watch.done and _following(watch.key) is not None


def _hold(receiver: Receiver, feed: Feed, watch: Watch | None = None) -> None:
    """Держим показ: опрос приёмника раз в 2 с, упаковка должна быть жива, из RAM уходит
    только пройденное, сторож раз в 10 с пишет позицию.

    Перемотку здесь ловить больше нечем и незачем: приёмник видит весь фильм и на seek
    просто просит сегмент нужного места, а :class:`Feed` пакует оттуда (§2.1 SPEC-v2).
    Показу остаётся то, о чём раздача не знает: пауза на пульте и конец показа.

    Придерживать ffmpeg сигналом (SIGSTOP) здесь больше нечем и незачем: темп держит
    сам ffmpeg (``-readrate`` + ``-readrate_initial_burst``), а под паузой процесс
    именно завершается — под SIGSTOP'ом приёмник намертво вис в BUFFERING.
    """
    paused, said, seen = 0.0, 0.0, False
    #: Позиция приёмника с прошлого опроса — от неё считается запас показа. Прошлая, а не
    #: сегодняшняя, потому что запас нужен раньше, чем приходит ответ приёмника, и взять
    #: его больше неоткуда. На решение сторожа это не влияет: нудж срабатывает только
    #: после :attr:`STALL_SECONDS` неподвижности, то есть когда прошлая позиция и есть
    #: сегодняшняя. А сразу после перемотки, где число ещё старое, позиция изменилась —
    #: и счётчик подвиса обнулён.
    last = 0.0
    trace = bool(os.environ.get(TRACE_ENV))
    while True:
        _ctl(receiver)
        if trouble := feed.trouble():
            # Убитый сигналом ffmpeg ничего сказать не успевает — не выдумываем за него.
            raise InfraError(f"упаковка оборвалась: {trouble}")
        try:
            # Запас упаковки идёт приёмнику: неподвижный BUFFERING при готовых сегментах
            # впереди — это зависание, а при пустых — законное ожидание нас (§6 SPEC-v2).
            position = receiver.position(feed.front(last))
        except InfraError:  # приёмник позицию не отдаёт — показу остаётся только ждать
            time.sleep(2.0)
            continue
        last = position.pos
        if not seen and position.state == "PLAYING":
            # Картинка на экране — теперь CLI имеет право сказать «старт NN с» (§4).
            seen = True
            mark_playing(feed.out)
        if trace:
            front = feed.front(position.pos)
            print(
                f"запас: показ {position.pos:.0f} · упаковано {front:.0f} · "
                f"впереди {front - position.pos:.0f} с · {feed.weight() / 1e6:.0f} МБ · "
                f"расхождение с манифестом {feed.drift():.3f} с · {position.state}",
                flush=True,
            )
        if time.monotonic() - said >= SAY_SECONDS:
            # Что видит приёмник, тем и отчитываемся: длительность и позиция — это ровно
            # ``duration`` и ``current_time`` из MEDIA_STATUS, снятые владеющим сендером.
            # Другого доказательства «на ТВ есть таймлайн» у нас нет (§9).
            said = time.monotonic()
            print(
                f"экран: {_hms(position.pos)} из {_hms(position.dur)} · {position.state}",
                flush=True,
            )
        if watch is not None:
            watch.see(position.pos)
            if watch.done and watch.entry.serial:
                return  # серия досмотрена — освобождаем показ под следующую
        if position.state == "PAUSED":
            paused = paused or time.monotonic()
            if time.monotonic() - paused > PAUSE_LIMIT:
                return  # пауза длиной с вечер — показ окончен, юнит гасим
            if time.monotonic() - paused > PAUSE_SECONDS and not feed.halted():
                print("пауза на пульте — упаковку гашу", flush=True)
                feed.halt()  # вернутся к показу — раздача сама начнёт паковать заново
        elif not position.playing:
            return
        else:
            paused = 0.0
            if feed.recoder is not None:
                feed.recoder.played = position.pos
            feed.prune(position.pos)
        time.sleep(2.0)


@runtime_checkable
class _Steerable(Protocol):
    """Приёмник, которым можно управлять как с пульта (:data:`CTL_ENV`)."""

    def seek(self, pos: float) -> None: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...


def _ctl(receiver: Receiver) -> None:
    """Исполнить команду диагностического пульта, если она положена (:data:`CTL_ENV`).

    Файл съедается до исполнения: команда одноразовая, и повторить её на следующем опросе
    нельзя даже при осечке приёмника — иначе одна опечатка мотала бы фильм вечно.
    """
    name = os.environ.get(CTL_ENV)
    if not name or not isinstance(receiver, _Steerable):
        return
    path = Path(name)
    try:
        line = path.read_text("utf-8").strip()
    except OSError:
        return
    path.unlink(missing_ok=True)
    if not line:
        return
    word, _, rest = line.partition(" ")
    print(f"пульт: {line}", flush=True)
    with contextlib.suppress(Exception):
        if word == "seek":
            receiver.seek(float(rest))
        elif word == "pause":
            receiver.pause()
        elif word == "play":
            receiver.resume()


def liveliness(plan: _Plan) -> int:
    """Насколько картина живая — сиды у той раздачи, которая реально поедет на ТВ.

    Мерок было три, и две отброшены на живой выдаче:

    * сумма сидов по всем релизам — вытягивает картину числом раздач, а не их
      качеством: у «Матрицы» 1999 сорок релизов против одиннадцати у «Воскрешения»,
      и сумма выбрала бы первую даже с мёртвыми DVD-рипами в хвосте;
    * сиды :attr:`~torrcast.parse.Picture.best_release` — не знают ни про потолок
      битрейта, ни про образы дисков, ни про старьё, а это и есть отбор.

    Осталось честное: берём верх :func:`rank_releases` — то, что Enter и запустит, —
    и считаем его сиды. Годным он обязан быть по :func:`is_candidate`: негодный верх
    (у «Тачек» 2006 это 41-гигабайтный 4K-ремукс на 49.9 Мбит/с, выше потолка
    декодера) означает, что играть у картины нечего, и вес у неё ноль. Заодно сюда
    сам собой затекает :func:`is_dated`: обсиженный .avi больше не тянет картину
    наверх, потому что верхом он уже не бывает.
    """
    top = plan.ranked[0] if plan.ranked else None
    if top is None or not is_candidate(top, plan.runtime, plan.warn_mbit):
        return 0
    return top.seeders


def liveliest(plans: list[_Plan]) -> int:
    """Номер (с единицы) самой живой картины — он же дефолт меню и первый на прогрев.

    Список остаётся хронологическим (§2 SPEC-v2), меняется только цифра в скобках:
    «моана» печатает четыре картины и предлагает вторую, а не немую документалку
    1926 года. Равный вес — берём раннюю: при ничьей хронология и есть ответ.
    """
    return max(range(1, len(plans) + 1), key=lambda n: (liveliness(plans[n - 1]), -n))


def warm_order(plans: list[_Plan]) -> list[_Plan]:
    """Кого греть под меню и в каком порядке: сначала дефолт, дальше по хронологии.

    Раньше грелись ``plans[:PREWARM]`` — первые ПО ХРОНОЛОГИИ, потому что дефолтом был
    первый пункт. С живым дефолтом это разъехалось бы ровно там, где больнее всего: у
    «моаны» дефолт — вторая картина, у «аватара» — девятая из десяти, а прогрето было
    бы 1–3. Enter попадал бы в непрогретую картину, и §7.2 (0.6–2.7 с до готовности
    LOAD) держится как раз на том, что карта опорных кадров и голова файла легли в кэш
    ещё под вопросом; без прогрева это снова 3–6 с одного только роя.

    Остальные картины греются по хронологии не от лени: список на экране хронологический,
    и человек, который не соглашается с дефолтом, чаще всего тычет в соседний номер.
    """
    default = liveliest(plans)
    return [plans[default - 1]] + [p for n, p in enumerate(plans, start=1) if n != default]


def _pick_plan(plans: list[_Plan]) -> _Plan:
    """Вопрос «какой фильм франшизы?» (§2 SPEC-v2); один вариант — без вопроса.

    Дефолт — самая живая картина (:func:`liveliest`), а не первая по хронологии. До
    этого Enter на «моане» запускал «Моану: романтику золотого века» 1926 года: немое
    документальное кино, один VHS-рип, 5 сидов — то есть человек, ответивший так, как
    приглашает строка `[1]`, гарантированно не получал ничего.

    Без терминала (ssh без pty, cron, чужой скрипт) спрашивать некого, и §3 SPEC-v2 велит
    не висеть, а брать дефолт. Здесь мы по-прежнему отказываемся — и «дефолт стал умнее»
    ничего не меняет. У озвучки дефолт считается правилами, у «Продолжить?» это
    «продолжить», а тут любой дефолт означает **другой фильм**: разница между «Моаной»
    2016 и «Моаной 2» — это не оттенок, а не тот вечер. Цифра в скобках имеет смысл
    ровно потому, что рядом напечатан список и человек видит, от чего отказывается;
    без терминала видеть его некому. Поэтому отказываемся вслух и подсказываем, как
    назвать картину точно.
    """
    if len(plans) == 1:
        print(f"  1. {_named(plans[0].picture)}")
        return plans[0]
    for number, plan in enumerate(plans, start=1):
        print(f"  {number}. {_named(plan.picture)}")
    default = liveliest(plans)
    if not console.stdin_is_tty():
        raise NotFoundError(
            f"подходит картин: {len(plans)}, а терминала нет — вслепую не выбираю; "
            f"назови картину точно (например «{plans[default - 1].picture.title}») "
            "или запусти cast в терминале"
        )
    return plans[ask("Что смотрим?", len(plans), default=default) - 1]


def _named(picture: Picture) -> str:
    kind = ", сериал" if picture.kind == "tv" else ""
    return f"{picture.title} ({picture.year or '?'}{kind})"


def warned(release: Release, runtime: float, warn_mbit: float, recode_at: float = 0.0) -> str:
    """Почему релиз не дефолт: HEVC ресивер может не потянуть, жирный битрейт — тоже (§3).

    Словами, а не значками: ``⚠`` из вывода убран целиком (§3 SPEC-v2) — в терминале
    владельца он не нёс смысла и разъезжался по ширине.
    """
    peak = bitrate_of(release, runtime)
    marks = ["не берём"] if release.is_hevc else []
    if peak > warn_mbit:
        marks += ["тяжёлый"]
    elif recode_at > 0 and peak > recode_at:
        # §6.2: не брак, а честное предупреждение — тяжёлые куски поедут перекодированными.
        marks += ["перекодируем"]
    return ", ".join(marks)


def quality_text(release: Release, media: Media) -> str:
    """Разрешение, которое реально поедет на ТВ. ffprobe уже прочитан — врать нечем.

    Порядок именно такой: сначала подтверждённая высота кадра, и только если ffprobe её
    не отдал (экзотика, битый заголовок) — заявка из имени. До 06-08-2026 было наоборот,
    и «Моана 2» печаталась 1080p при 1150×574 внутри: заявка выигрывала у факта, то есть
    ровно та молчаливая подмена, которую запрещает §1 v1.
    """
    return media.quality if media.height else (release.quality or "?")


def understated(release: Release, media: Media) -> str:
    """Чем подтверждённое разрешение хуже обещанного; пусто — релиз честен.

    Две половины, и обе взяты с живой выдачи «моаны 2» (06-08-2026):

    1. имя называет разрешение, а внутри заметно меньше (:data:`HONEST_RATIO`);
    2. имя не называет ничего, а внутри не HD вовсе (:data:`HD_HEIGHT`) — это и есть
       верхний кандидат «Моаны 2»: ``WEB-DL-AVC`` без единой цифры в заголовке, 3.14 ГБ,
       140 сидов, а на деле 1150×574.

    Возвращает кусок фразы, а не флаг: строка про подмену обязана назвать обе цифры,
    иначе она ничего не объясняет.
    """
    if not media.height:  # ffprobe высоту не отдал — сравнивать не с чем, молчим
        return ""
    if release.height:
        if media.frame < release.height * HONEST_RATIO:
            return f"назван {release.quality}, на деле {media.quality}"
        return ""
    return f"на деле {media.quality}" if media.frame < HD_HEIGHT else ""


def promises_more(release: Release, media: Media) -> bool:
    """Стоит ли вообще смотреть на этот запасной: обещает HD и больше, чем дал верх."""
    return release.height >= HD_HEIGHT and release.height > media.frame


def honest_shot(release: Release, media: Media) -> bool:
    """Запасной подтвердил своё имя: кадр из ffprobe не ниже заявленной ступени. Имя
    молчало — тогда достаточно, чтобы внутри оказался HD.
    """
    if not media.height:
        return False
    if release.height:
        return media.frame >= release.height * HONEST_RATIO
    return media.frame >= HD_HEIGHT


def is_disc(release: Release) -> bool:
    """Образ диска (DVD-Video, BDMV, ISO): цельного файла внутри нет — не дефолт (§1)."""
    return bool(_DISC_RE.search(release.raw_name))


def is_candidate(release: Release, runtime: float, warn_mbit: float) -> bool:
    """Кандидат в дефолт (§2.1): первый сорт (:attr:`Release.prime`), не образ диска и в
    пределах потолка декодера. Жирнее потолка — в таблице остаётся с ⚠, но Enter его не
    возьмёт: ресивер на таком битрейте встаёт (§3, §9).
    """
    return release.prime and not is_disc(release) and bitrate_of(release, runtime) <= warn_mbit


def is_dated(release: Release, runtime: float) -> bool:
    """Раздача пахнет старьём — до всякого ffprobe, по имени и размеру (§7.1 SPEC-v2).

    Две половины признака, и они не взаимозаменяемы:

    1. :attr:`Release.dated` — имя признаётся само: XviD/DivX, ``.avi``, DVDRip/VHSRip/
       SATRip/TVRip/CAM.
    2. Имя не называет НИЧЕГО (ни разрешения, ни кодека), а размер даёт меньше
       :data:`SD_BITRATE` Мбит/с. Это и есть та раздача, ради которой всё затевалось:
       «Моана 2 … WEB-DL] Dub (MovieDalen)», 221 сид, 1.46 ГБ — в заголовке rutracker
       ни слова про кодек, а внутри ``Moana.2.2024.WEB-DLRip.ELEKTRI4KA.avi``
       (проверено по самому .torrent). Ни один маркер из пункта 1 её не ловит.

    Почему это в cli, а не свойством релиза рядом с ``dated``: второй половине нужна
    длительность картины, а её знает только план (:class:`_Plan`), не парсер. Ровно та
    же причина держит здесь :func:`bitrate_of` и :func:`is_candidate`.

    ⚠️ Сериалу вторая половина не считается: в раздаче лежит весь сезон, и «6 ГБ» это
    не битрейт фильма, а восемь серий (:func:`bitrate_of` по той же причине отдаёт для
    сериала ноль). Значит подтверждённый .avi «Легенды об Аанге» 2024 года эвристика
    по-прежнему НЕ понижает — ловит его только ffprobe. Чинится это счётом серий, а не
    порогом, и в объём этой правки не влезло.

    Признак меняет только ПОРЯДОК: годность решает ffprobe, а :func:`is_candidate` его
    не спрашивает — иначе у картины, где ни в одном имени нет маркера качества, не
    осталось бы ни одного кандидата.
    """
    if release.dated:
        return True
    if release.quality or release.codec or release.kind == "tv":
        return False
    return 0.0 < bitrate_of(release, runtime) < SD_BITRATE


def rank_releases(releases: list[Release], runtime: float, warn_mbit: float) -> list[Release]:
    """Порядок меню (§2.1, §3): сверху самый обсиженный кандидат, потом всё остальное по
    сидам, образы дисков всегда внизу — цельного файла внутри нет, стримить нечего.

    Между «кандидат» и «сиды» вклинена ступень :func:`is_dated` (§7.1 SPEC-v2): обсиженное
    старьё уступает место годному даже при кратной разнице в сидах. Цена вопроса
    измерена: раздача, которую ffprobe отбраковывает как ``mpeg4``, стоит 2–5 секунд
    живого старта — метаданные по DHT плюс чтение дорожек, — и это ровно те секунды,
    которые §4 велит вынести из критического пути. На «Моане 2» так и было: первым
    кандидатом стоял 1.46-гигабайтный .avi с 221 сидом, а годный WEB-DL-AVC с 140
    сидами ждал своей очереди вторым.

    Внутри каждой группы всё как было — сиды, потом размер.
    """
    return sorted(
        releases,
        key=lambda r: (
            is_disc(r),
            not is_candidate(r, runtime, warn_mbit),
            is_dated(r, runtime),
            -r.seeders,
            -r.size,
        ),
    )


def bitrate_of(release: Release, duration: float) -> float:
    """Оценка битрейта по размеру раздачи — только для фильма. У сериала в раздаче лежит
    весь сезон, а не серия: «9.7 ГБ» это 3 Мбит/с на серию, а не 30, и по такой оценке
    самые обсиженные раздачи сезона улетали бы вниз с ⚠. Сериалу битрейт меряется по
    файлу серии, когда он открыт и прочитан ffprobe (§3, реестр ТВ-рисков §9).
    """
    return 0.0 if release.kind == "tv" else bitrate_mbit(release.size, duration)


def render_table(
    releases: list[Release],
    runtime: float,
    warn_mbit: float,
    limit: int = TABLE_LIMIT,
    recode_at: float = 0.0,
) -> str:
    """Таблица релизов §2.1: № · качество · размер · сиды · озвучка · кодек. Битрейт для пометки
    прикидывается по размеру и типовой длительности, пока настоящая не прочитана ffprobe
    (§3, реестр ТВ-рисков §9); ниже ``limit`` — раздачи без сидов, выбирать там нечего.
    """
    shown = releases[:limit]
    rows = [
        (
            str(number),
            r.quality or "?",
            _gb(r.size),
            str(r.seeders),
            _cut(", ".join(r.voices) or "—", 34),
            ((r.codec or "?") + " " + warned(r, runtime, warn_mbit, recode_at)).strip(),
        )
        for number, r in enumerate(shown, start=1)
    ]
    head = ("№", "Качество", "Размер", "Сиды", "Озвучка", "Кодек")
    width = [max(len(c[i]) for c in (head, *rows)) for i in range(len(head))]

    def line(cells: tuple[str, ...]) -> str:
        return "  " + "  ".join(_pad(c, w) for c, w in zip(cells, width, strict=True))

    out = ["Релизы:", line(head), *(line(row).rstrip() for row in rows)]
    if len(releases) > len(shown):
        out.append(f"  … и ещё {len(releases) - len(shown)} с меньшим числом сидов")
    return "\n".join(out)


def pick_voice(media: Media, args: Args, remembered: str = "") -> tuple[int, str]:
    """Какую дорожку играем и что после этого лежит в памяти картины.

    Правка владельца 06-08 к §2 SPEC-v2: **на счастливом пути вопроса про озвучку нет**.
    Дорожка выбирается сама (:meth:`Media.default_track`), и её подпись печатается в
    строке запуска — молчаливых подмен не бывает (§1 v1).

    Спросить можно только явно: ``--voice N`` берёт дорожку N, ``--voice`` без номера
    показывает меню. Оба — явный выбор, и только он пишется в память картины
    (:attr:`torrcast.state.Entry.voice`). Автовыбор память не трогает: иначе первый же
    запуск с другим релизом переписал бы то, что владелец выбрал руками.

    Возвращает пару «номер дорожки в этом релизе, память картины».
    """
    if not media.tracks:
        raise InfraError("в файле нет звуковых дорожек")
    if args.voice is not None:
        index = _ask_voice(media) if args.voice == VOICE_MENU else _voice_number(media, args.voice)
        return index, media.tracks[index].label
    if remembered:
        found = media.find_voice(remembered)
        if found is not None:
            return found, remembered
        # Память живёт на картину, а релиз временный: озвучки в нём нет — говорим и
        # играем обычную, но выбор владельца не забываем (:attr:`Entry.voice`).
        print(f"озвучки «{remembered}» в этом релизе нет — беру обычную")
    return media.default_track(), remembered


def _voice_number(media: Media, number: int) -> int:
    """Номер дорожки от человека → индекс; чужого номера нет — честная строка (§1)."""
    if not 1 <= number <= len(media.tracks):
        raise NotFoundError(
            f"дорожек {len(media.tracks)}, номера {number} нет — посмотри: cast voices <запрос>"
        )
    return number - 1


def _ask_voice(media: Media) -> int:
    """Меню озвучек — только по ``--voice`` без номера. Дефолт тот же, что и без флага."""
    default = media.default_track()
    if len(media.tracks) == 1:  # выбора нет — вопроса тоже
        return default
    print(voices_table(media, default))
    return ask("Озвучка?", len(media.tracks), default=default + 1) - 1


def voices_table(media: Media, default: int, remembered: str = "") -> str:
    """Список озвучек с пометками «дефолт» и «запомнено» — для меню и ``cast voices``."""
    found = media.find_voice(remembered) if remembered else None
    rows = []
    for track in media.tracks:
        marks = (("дефолт", track.index == default), ("запомнено", track.index == found))
        note = [word for word, on in marks if on]
        tail = f"   [{', '.join(note)}]" if note else ""
        rows.append(f"  {track.index + 1}. {track.label}{tail}")
    return "\n".join(["Озвучка:", *rows])


def _gb(size: int) -> str:
    return f"{size / 1024**3:.1f} ГБ" if size else "—"


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _pad(text: str, width: int) -> str:
    return text + " " * (width - len(text))


def _hms(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


if __name__ == "__main__":
    raise SystemExit(main())
