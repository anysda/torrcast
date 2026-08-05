"""CLI — единственный наш процесс (§3 ТЗ).

Контракт (§5 v1 + §2 SPEC-v2): ``cast <запрос> [sNeM] [--new] [--dry]``, отладочные
ручки ``--release N`` / ``--file N`` / ``cast releases <запрос>``, а также ``cast stop``,
``cast status``, ``cast doctor``, ``cast --tv <ip>``. Коды выхода: ``0`` ок · ``1`` не
нашли · ``2`` инфра-ошибка; наружу — короткие русские строки без трейсбеков (§6).

Счастливый путь §2 SPEC-v2 — два вопроса и ни одного упоминания файлов: «какой фильм
франшизы?» и «какая озвучка?», оба пропускаются при единственном варианте. Релиз
выбирается сам, а таблица релизов и список файлов уезжают в отладочные ручки.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import signal
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from torrcast import InfraError, NotFoundError, TorrcastError, __version__
from torrcast.cast import Receiver, make_receiver
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
from torrcast.search import Prowlarr, to_releases
from torrcast.state import Config, Entry, State, load_config, save_config
from torrcast.stream import (
    Feed,
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
)

__all__ = ["Args", "bitrate_of", "main", "parse_args", "rank_releases", "render_table"]

EXIT_OK, EXIT_NOT_FOUND, EXIT_INFRA = 0, 1, 2
#: Сколько строк таблицы релизов показываем: ниже начинаются раздачи без сидов.
TABLE_LIMIT = 12
#: Сколько релизов подряд проверяем ffprobe, прежде чем сдаться (§1: подмены не молчат).
MAX_TRIES = 3
#: Сколько картин франшизы греем под меню: топ-2–3 релиза уходят в TorrServer фоном,
#: пока человек отвечает на вопросы (§4 SPEC-v2).
PREWARM = 3
#: Бюджет одной раздачи на метаданные по DHT, секунды. Не уложилась — не «зависли
#: насмерть», а честная строка и следующий релиз (дефект №1 владельца, §1 SPEC-v2).
META_BUDGET = 20.0
#: Бюджет на чтение дорожек (ffprobe) той же раздачи, секунды.
PROBE_BUDGET = 40.0
#: Как часто сторож кладёт позицию в state, секунды (§3).
WATCH_SECONDS = 10.0
#: Как часто показ пишет в журнал, что видит приёмник (§2.1 SPEC-v2): позиция и общее
#: время — единственное доказательство того, что на экране есть таймлайн (§9).
SAY_SECONDS = 30.0
#: Сколько терпим паузу на пульте, прежде чем погасить упаковку (§6 SPEC-v2): дальше
#: сегменты копились бы в tmpfs впустую — приёмник их не забирает.
PAUSE_SECONDS = 60.0
#: Пауза длиннее этого — показ считается оконченным: юнит гаснет и не держит раздачу.
PAUSE_LIMIT = 3600.0
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
    audio: int | None = None
    new: bool = False
    dry: bool = False
    #: Внутреннее: показ внутри transient-юнита, руками не зовётся.
    play_key: str | None = None

    @property
    def command(self) -> str:
        """``stop`` / ``status`` / ``doctor`` / ``releases`` / ``play`` / ``configure`` /
        ``worker``.
        """
        if self.play_key:
            return "worker"
        if self.query and self.query[0] in {"stop", "status", "doctor", "releases"}:
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
    parser.add_argument("--audio", type=int, metavar="N", help="взять дорожку N без меню")
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
            if command == "worker":
                return _cmd_worker(str(args.play_key))
            return _cmd_play(args)
    except NotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_NOT_FOUND
    except TorrcastError as exc:  # InfraError и всё прочее наше
        print(str(exc), file=sys.stderr)
        return EXIT_INFRA
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
        print(render_table(plan.ranked, plan.runtime, plan.warn_mbit))
    print()
    print("играть конкретный: cast <запрос> --release N [--file N]")
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
    """
    config = load_config()
    # SIGTERM от `cast stop` обязан пройти через finally: иначе позиция не запишется.
    signal.signal(signal.SIGTERM, _on_term)
    torrserver = TorrServer(config.torrserver_url)
    magnet, torrent_hash = "", ""
    while True:
        entry = State.load().get(key)
        if entry is None:
            raise InfraError(f"в состоянии нет записи {key}")
        if entry.magnet != magnet:  # раздача та же — метаданные второй раз не ждём
            magnet = entry.magnet
            torrent_hash = torrserver.add(magnet)
            torrserver.wait_files(torrent_hash)
        source = torrserver.stream_url(torrent_hash, entry.file_idx)
        entry = _duration(key, entry, source)
        watch = Watch(key=key, entry=entry)
        title = " ".join(filter(None, (entry.title, entry.label)))
        print(f"показ «{title}» с {_hms(entry.pos)}", flush=True)
        code = _play(config, source, entry.audio, title, _Clock(), watch)
        following = State.load().get(key)
        if not watch.done or following is None or following.done or not following.label:
            return code
        print(f"следующая серия: {following.label}", flush=True)


def _duration(key: str, entry: Entry, source: str) -> Entry:
    """Длительность серии для порога 95 % (§2.4): следующая серия своей ещё не знает —
    её длительность лежит в её же файле, и читается она из потока, как дорожки (§3).
    """
    if entry.dur > 0:
        return entry
    entry.dur = probe(source).duration
    state = State.load()
    state.put(key, entry)
    state.save()
    return entry


def _on_term(_signal: int, _frame: object) -> None:
    raise KeyboardInterrupt


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
    """
    clock = _Clock()
    config = load_config()
    state = State.load()
    found_entry = state.find(args.title_query)
    if found_entry is not None and args.new:  # --new: забыть прогресс и выбрать заново (§4)
        state.drop(found_entry[0])
        state.save()
    elif found_entry is not None:
        code = _continue(config, *found_entry, args=args, clock=clock)
        if code is not None:
            return code

    with Progress() as progress:
        plans = _search(config, args, progress)
        torrserver = TorrServer(config.torrserver_url)
        bench = _Bench(torrserver, choose=_file_picker(args))
        # Прогрев под меню (§4 SPEC-v2): пока идёт вопрос, раздачи уже качают метаданные.
        for plan in plans[:PREWARM]:
            bench.start(plan, plan.first)
        plan = _pick_plan(plans)
        prep = bench.resolve(plan, args, progress)

    release, video, media = prep.release, prep.want, prep.found
    audio = _ask_audio(media, args)
    label = media.tracks[audio].label if audio < len(media.tracks) else "—"
    series = plan.series
    what = f"«{plan.picture.title}»" + (
        f" {series.want}" if series else f" ({plan.picture.year or '?'})"
    )
    about = f"{what} · {release.quality or media.quality} · {label}"
    # Настоящий битрейт: размер файла серии/фильма на его же длительность, а не оценка.
    peak = bitrate_mbit(video.size, media.duration or plan.runtime)
    if peak > config.bitrate_warn_mbit:
        print(f"внимание: ~{peak:.0f} Мбит/с — ресивер на таком битрейте может встать")
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
        dur=media.duration,
        query=slugify(args.title_query),
        season=series.want.season if series else None,
        episode=series.want.episode if series else None,
        episodes=series.table if series else [],
    )
    return _launch(config, plan.picture.key, entry, about, clock)


def _search(config: Config, args: Args, progress: Progress) -> list[_Plan]:
    """Поиск и разбор выдачи: запрос → картины франшизы, каждая со своим пулом релизов."""
    from torrcast.parse import cluster, pick_franchise

    if not config.prowlarr_apikey:  # без Prowlarr искать нечем — это инфра-ошибка
        raise InfraError("не настроен Prowlarr: apikey пуст, перезапусти ./install.sh")
    query = args.title_query
    name, _ = split_franchise_index(query)
    progress.phase(f"поиск «{name}»")
    raw = Prowlarr(config.prowlarr_url, config.prowlarr_apikey).search(name)
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
    ranked = rank_releases(pool, runtime, config.bitrate_warn_mbit)
    return _Plan(
        picture=picture,
        ranked=ranked,
        runtime=runtime,
        warn_mbit=config.bitrate_warn_mbit,
        series=series,
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
    warn_mbit: float
    series: _Series | None = None

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
        return _resume(config, key, entry, clock=clock, dry=args.dry) if entry.resumable else None
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


def _about(entry: Entry) -> str:
    """Строка показа по записи состояния: «Киберпанк» · s1e2 · дорожка 1 · с 0:03:20."""
    parts = [f"«{entry.title}»", entry.label, f"дорожка {entry.audio + 1}"]
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
            trouble = self._trouble(prep, pinned=args.pinned)
            if not trouble:
                progress.phase("")
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

    def _trouble(self, prep: _Prep, pinned: bool) -> str:
        """Почему релиз не годится; пусто — годится. Названный руками не подменяется."""
        if prep.error:
            return prep.error
        if prep.media is None or prep.video is None:
            return "поток не прочитан"
        codec = prep.media.video or "h264"
        return "" if pinned or codec == "h264" else codec

    def _forget(self, prep: _Prep) -> None:
        if prep.torrent_hash:
            self.torrserver.drop(prep.torrent_hash)

    def _work(self, plan: _Plan, prep: _Prep) -> None:
        """Фоновая подготовка: раздача в TorrServer, метаданные по DHT, ffprobe."""
        try:
            prep.phase = "метаданные (DHT)"
            prep.torrent_hash = self.torrserver.add(prep.release.magnet)
            files = self.torrserver.wait_files(prep.torrent_hash, timeout=self.meta_budget)
            prep.meta = time.monotonic() - prep.started
            prep.video = self.choose(plan, prep.release, files)
            prep.phase = "дорожки"
            mark = time.monotonic()
            source = self.torrserver.stream_url(prep.torrent_hash, prep.want.index)
            prep.media = probe(source, timeout=self.probe_budget)
            prep.read = time.monotonic() - mark
            prep.phase = "готово"
        except TorrcastError as exc:
            prep.error = str(exc)
            prep.phase = "сбой"
        finally:
            prep.ready.set()


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


def _resume(config: Config, key: str, entry: Entry, clock: _Clock, dry: bool = False) -> int:
    """Возобновление §2.3: один вопрос и сразу показ. Релиз, файл и дорожка берутся из
    состояния — ни поиска, ни меню, поэтому старт укладывается в 5–15 с (§3.1).
    """
    question = f"«{entry.title}» остановились на {_hms(entry.pos)}. Продолжить? [Да/сначала]"
    answer = ask_line(question)
    if answer[:1] in {"с", "s", "н", "n"}:  # «сначала» / «с начала» / «нет»
        entry.pos = 0.0
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
    with Progress() as progress:
        _await_playing(config, progress)
    print(f"играю {about} — на ТВ   (старт {clock.total:.0f} с)")
    return EXIT_OK


def _await_playing(config: Config, progress: Progress, timeout: float = 120.0) -> None:
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
            progress.phase("")
            return
        if not packed:
            with contextlib.suppress(OSError):
                packed = any(out.glob("v*.ts"))
        progress.phase("жду телевизор" if packed else "упаковка")
        if not unit_active():
            progress.phase("")
            raise InfraError(f"показ не запустился: {unit_why()}")
        time.sleep(0.5)
    progress.phase("")
    stop_play_unit()
    raise InfraError(f"показ не начался за {timeout:.0f} с — {unit_why()}")


def _play(
    config: Config,
    source: str,
    audio: int,
    about: str,
    clock: _Clock,
    watch: Watch | None = None,
    duration: float = 0.0,
) -> int:
    """Упаковка → раздача по http на голом IP (§5 SPEC-v2) → приёмник. Своих демонов
    нет: и ffmpeg, и раздача живут ровно на время показа и гасятся вместе с ним, что бы
    ни случилось.

    Упаковка за показ перезапускается столько раз, сколько человек перемотал (§2.1
    SPEC-v2): манифест обещает приёмнику весь фильм, а :class:`Feed` пакует то место,
    которое он попросил. Раздача, приёмник и LOAD при этом одни на весь показ.
    """
    from torrcast.stream import hls_base, hls_dir, slot_at

    out = hls_dir(config.hls_dir)
    start = watch.entry.pos if watch else 0.0
    length = watch.entry.dur if watch else duration
    tls = config.transport == "https"
    feed = Feed(
        source=source,
        audio=audio,
        out=out,
        duration=length,
        readrate=config.hls_readrate,
        burst=config.hls_burst,
        keep=config.hls_keep,
        log=lambda text: print(text, flush=True),
    )
    server = HlsServer(
        out, config.hls_cert, config.hls_key, port=config.hls_port, tls=tls, feed=feed
    )
    # Серт приёмнику нужен только затем, чтобы проверить нашу раздачу: по http проверять
    # нечего, и mock не должен делать вид, что что-то проверил.
    receiver = make_receiver(config.receiver, config.tv or "", config.hls_cert if tls else "")
    url = f"{hls_base(config)}/index.m3u8"
    try:
        server.start()
        # Упаковку начинаем сами, не дожидаясь первого запроса: ресиверу нужен готовый
        # кусок сразу, иначе LOAD упирается в ожидание ffmpeg и старт растёт на глазах.
        feed.restart(slot_at(start))
        receiver.play(url, about, at=start)
        print(f"играю {about} — на ТВ   (старт {clock.total:.0f} с)", flush=True)
        _hold(receiver, feed, watch)
    finally:
        with contextlib.suppress(TorrcastError):
            receiver.stop()
        feed.stop()
        server.stop()
        if watch is not None:  # позиция фиксируется при любом исходе, включая SIGTERM
            watch.flush()

    report = getattr(receiver, "report", None)
    if report is None:
        return EXIT_OK
    print(report.line())
    # Серию обрывают намеренно на пороге 95 % — хвост упаковки декодеру и не отдавали.
    if not report.ok and not (watch is not None and watch.done):
        raise InfraError("приёмник не досмотрел поток — цифры выше")
    return EXIT_OK


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
    while True:
        if trouble := feed.trouble():
            # Убитый сигналом ffmpeg ничего сказать не успевает — не выдумываем за него.
            raise InfraError(f"упаковка оборвалась: {trouble}")
        try:
            position = receiver.position()
        except InfraError:  # приёмник позицию не отдаёт — показу остаётся только ждать
            time.sleep(2.0)
            continue
        if not seen and position.state == "PLAYING":
            # Картинка на экране — теперь CLI имеет право сказать «старт NN с» (§4).
            seen = True
            mark_playing(feed.out)
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
            feed.prune(position.pos)
        time.sleep(2.0)


def _pick_plan(plans: list[_Plan]) -> _Plan:
    """Вопрос «какой фильм франшизы?» (§2 SPEC-v2); один вариант — без вопроса."""
    if len(plans) == 1:
        print(f"  1. {_named(plans[0].picture)}")
        return plans[0]
    for number, plan in enumerate(plans, start=1):
        print(f"  {number}. {_named(plan.picture)}")
    return plans[ask("Что смотрим?", len(plans)) - 1]


def _named(picture: Picture) -> str:
    kind = ", сериал" if picture.kind == "tv" else ""
    return f"{picture.title} ({picture.year or '?'}{kind})"


def warned(release: Release, runtime: float, warn_mbit: float) -> str:
    """Почему релиз не дефолт: HEVC ресивер может не потянуть, жирный битрейт — тоже (§3).

    Словами, а не значками: ``⚠`` из вывода убран целиком (§3 SPEC-v2) — в терминале
    владельца он не нёс смысла и разъезжался по ширине.
    """
    marks = ["не берём"] if release.is_hevc else []
    marks += ["тяжёлый"] if bitrate_of(release, runtime) > warn_mbit else []
    return ", ".join(marks)


def is_disc(release: Release) -> bool:
    """Образ диска (DVD-Video, BDMV, ISO): цельного файла внутри нет — не дефолт (§1)."""
    return bool(_DISC_RE.search(release.raw_name))


def is_candidate(release: Release, runtime: float, warn_mbit: float) -> bool:
    """Кандидат в дефолт (§2.1): первый сорт (:attr:`Release.prime`), не образ диска и в
    пределах потолка декодера. Жирнее потолка — в таблице остаётся с ⚠, но Enter его не
    возьмёт: ресивер на таком битрейте встаёт (§3, §9).
    """
    return release.prime and not is_disc(release) and bitrate_of(release, runtime) <= warn_mbit


def rank_releases(releases: list[Release], runtime: float, warn_mbit: float) -> list[Release]:
    """Порядок меню (§2.1, §3): сверху самый обсиженный кандидат, потом всё остальное по
    сидам, образы дисков всегда внизу — цельного файла внутри нет, стримить нечего.
    """
    return sorted(
        releases,
        key=lambda r: (is_disc(r), not is_candidate(r, runtime, warn_mbit), -r.seeders, -r.size),
    )


def bitrate_of(release: Release, duration: float) -> float:
    """Оценка битрейта по размеру раздачи — только для фильма. У сериала в раздаче лежит
    весь сезон, а не серия: «9.7 ГБ» это 3 Мбит/с на серию, а не 30, и по такой оценке
    самые обсиженные раздачи сезона улетали бы вниз с ⚠. Сериалу битрейт меряется по
    файлу серии, когда он открыт и прочитан ffprobe (§3, реестр ТВ-рисков §9).
    """
    return 0.0 if release.kind == "tv" else bitrate_mbit(release.size, duration)


def render_table(
    releases: list[Release], runtime: float, warn_mbit: float, limit: int = TABLE_LIMIT
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
            ((r.codec or "?") + " " + warned(r, runtime, warn_mbit)).strip(),
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


def _ask_audio(media: Media, args: Args) -> int:
    """Выбор дорожки: одна дорожка — вопроса нет, дефолт — русская (§2.1)."""
    if not media.tracks:
        raise InfraError("в файле нет звуковых дорожек")
    if args.audio is not None:
        if not 1 <= args.audio <= len(media.tracks):
            raise NotFoundError(f"дорожек {len(media.tracks)}, номера {args.audio} нет")
        return args.audio - 1
    if len(media.tracks) == 1:  # выбора нет — вопроса тоже (§2 SPEC-v2)
        return 0
    print("Озвучка: " + "  ".join(f"{t.index + 1}. {t.label}" for t in media.tracks))
    return ask("Озвучка?", len(media.tracks), default=media.default_track() + 1) - 1


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
