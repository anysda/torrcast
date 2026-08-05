"""CLI — единственный наш процесс (§3 ТЗ).

Контракт (§5): ``cast <запрос> [sNeM] [--new] [--release N] [--audio N] [--dry]``,
``cast stop``, ``cast status``, ``cast --tv <ip>``. Коды выхода: ``0`` ок ·
``1`` не нашли · ``2`` инфра-ошибка; наружу — короткие русские строки без
трейсбеков (§6).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import signal
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from torrcast import InfraError, NotFoundError, TorrcastError, __version__
from torrcast.cast import Receiver, make_receiver
from torrcast.parse import (
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
    Media,
    Packer,
    TorrFile,
    TorrServer,
    bitrate_mbit,
    pick_video_file,
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
#: Как часто сторож кладёт позицию в state, секунды (§3).
WATCH_SECONDS = 10.0
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
    audio: int | None = None
    new: bool = False
    dry: bool = False
    #: Внутреннее: показ внутри transient-юнита, руками не зовётся.
    play_key: str | None = None

    @property
    def command(self) -> str:
        """``stop`` / ``status`` / ``play`` / ``configure`` / ``worker``."""
        if self.play_key:
            return "worker"
        if self.query and self.query[0] in {"stop", "status"}:
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


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """Разобрать argv по контракту §5."""
    about = "torrcast — найти релиз и кастить его на ТВ без скачивания"
    parser = argparse.ArgumentParser(prog="cast", description=about, allow_abbrev=False)
    parser.add_argument("query", nargs="*", help="название, либо stop / status")
    parser.add_argument("--tv", metavar="IP", help="разовая настройка адреса ТВ")
    parser.add_argument("--release", type=int, metavar="N", help="взять релиз N без меню")
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
        if command == "configure":
            return _cmd_configure(args)
        if command == "stop":
            return _cmd_stop()
        if command == "status":
            return _cmd_status()
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


def _cmd_configure(args: Args) -> int:
    """``cast --tv <ip>`` — единственная настройка (§5)."""
    config = load_config()
    config.tv = args.tv
    save_config(config)
    print(f"ТВ: {config.tv}")
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
    print(f"▶ {what} — {_hms(entry.pos)} / {_hms(entry.dur)}")
    print(
        f"   {key} · файл #{entry.file_idx} · дорожка {entry.audio + 1} · "
        f"{config.hls_base_url} → {config.receiver}"
    )
    return EXIT_OK


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
        watch = Watch(key=key, entry=entry, offset=entry.pos)
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

    Приёмник считает время от начала своего потока, а после resume поток начинается с
    ``-ss offset`` — поэтому в состояние идёт ``offset + pos``, абсолютная позиция в фильме.
    Порог 95 % — «досмотрено» (§2.4): фильму сброс с пометкой, сериалу следующая серия.
    """

    key: str
    entry: Entry
    offset: float = 0.0
    every: float = WATCH_SECONDS
    done: bool = False
    last: float = field(default_factory=time.monotonic)

    def see(self, pos: float) -> None:
        """Позиция от приёмника; на диск — не чаще раза в ``every`` секунд. Порог 95 %
        записывается сразу: на нём держится стык серий, ждать тика ещё 10 с незачем.
        """
        self.entry.pos = self.offset + pos
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
            print(
                f"досмотрено{what}: {_hms(self.entry.pos)} из {_hms(self.entry.dur)}", flush=True
            )


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
    """Основной сценарий §2.1: запрос → франшиза → релиз → дорожка → каст."""
    from torrcast.parse import cluster, pick_franchise
    from torrcast.stream import RUNTIME_GUESS

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

    if not config.prowlarr_apikey:  # без Prowlarr искать нечем — это инфра-ошибка
        raise InfraError("не настроен Prowlarr: apikey пуст, перезапусти ./install.sh")

    query = args.title_query
    name, _ = split_franchise_index(query)
    print(f"«{name}» — ищу…")
    prowlarr = Prowlarr(config.prowlarr_url, config.prowlarr_apikey)
    raw = prowlarr.search(name)
    releases = to_releases(raw)
    pictures = cluster(releases)
    if not pictures:
        raise NotFoundError(f"по запросу «{name}» ничего не разобралось")
    # Номер в запросе — позиция во франшизе, а не в общей выдаче (§2.2).
    found = pick_franchise(query, pictures)
    if not found:
        raise NotFoundError(f"«{query}» — такой картины во франшизе нет")
    print(
        f"найдено раздач: {len(raw)} → картин: {len(pictures)}, "
        f"во франшизе: {len(found)} (поиск {clock.lap()})"
    )

    picture = _pick_picture(found)
    # Сериалу выбор релиза и дорожки делается один раз на раздачу (§2.4); цель по
    # умолчанию — s1e1, явное указание `cast киберпанк s2e5` меняет и цель, и отбор.
    series = _Series(want=args.episode or Episode(1, 1)) if picture.kind == "tv" else None
    runtime = RUNTIME_GUESS.get(picture.kind, 7200.0)
    pool = picture.releases
    if series is not None:
        pool = [r for r in pool if r.covers(series.want.season)]
        if not pool:
            raise NotFoundError(f"«{picture.title}»: раздач с сезоном {series.want.season} нет")
    ranked = rank_releases(pool, runtime, config.bitrate_warn_mbit)

    print()
    print(render_table(ranked, runtime, config.bitrate_warn_mbit))
    number = _ask_release(ranked, args)

    torrserver = TorrServer(config.torrserver_url)
    number, video, media = _open_release(
        torrserver, ranked, number, runtime, config.bitrate_warn_mbit, clock,
        pinned=args.release is not None, choose=series.choose if series else _largest,
    )  # fmt: skip
    release = ranked[number - 1]
    audio = _ask_audio(media, args)

    # Настоящий битрейт: размер файла серии/фильма на его же длительность, а не оценка.
    peak = bitrate_mbit(video.size, media.duration or runtime)
    heavy = " ⚠" if peak > config.bitrate_warn_mbit else ""
    label = media.tracks[audio].label if audio < len(media.tracks) else "—"
    what = f"«{picture.title}»" + (f" {series.want}" if series else f" ({picture.year or '?'})")
    about = f"{what} · {release.quality or '?'} · {label}"
    print()
    if series is not None:
        print(f"Серии: {series.summary()}")
    print(
        f"Файл: {video.base} · {_gb(video.size)} · {_hms(media.duration)} · "
        f"{media.video or '?'} · ~{peak:.1f} Мбит/с{heavy}"
    )
    if args.dry:
        print(f"▶ (--dry) {about} — каста нет")
        return EXIT_OK
    entry = Entry(
        title=picture.title,
        magnet=release.magnet,
        kind="tv" if picture.kind == "tv" else "movie",
        file_idx=video.index,
        audio=audio,
        dur=media.duration,
        query=slugify(args.title_query),
        season=series.want.season if series else None,
        episode=series.want.episode if series else None,
        episodes=series.table if series else [],
    )
    return _launch(config, picture.key, entry, about, clock)


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


def _largest(_release: Release, files: list[TorrFile]) -> TorrFile:
    """Выбор файла для фильма: самый крупный видеофайл раздачи."""
    return pick_video_file(files)


def _continue(config: Config, key: str, entry: Entry, args: Args, clock: _Clock) -> int | None:
    """Продолжение по сохранённому выбору (§2.3, §2.4). ``None`` — состоянием не обойтись,
    дальше идёт обычный путь с поиском и меню.

    Сериал вопросов не задаёт вовсе: релиз, дорожка и список серий уже выбраны, а
    какую серию и с какого места играть — записано. Фильм спрашивает ровно одно (§2.3).
    """
    if entry.kind != "tv" or not entry.episodes:
        return _resume(config, key, entry, clock=clock, dry=args.dry) if entry.resumable else None
    if args.episode is not None:  # `cast киберпанк s2e5` — прыжок по кэшу раздачи
        jumped = entry.jump(args.episode.season, args.episode.episode)
        if jumped is None:
            return None  # серии в этой раздаче нет — честно идём искать релиз сезона
        return _launch(config, key, jumped, _about(jumped), clock, args.dry)
    if entry.done:  # конец раздачи: сама собой следующая серия не появится
        print(f"«{entry.title}» — {entry.label} была последней в раздаче")
        if _ask_line("Смотреть сначала? [Да/нет]")[:1] in {"н", "n"}:
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


def _open_release(
    torrserver: TorrServer,
    ranked: list[Release],
    number: int,
    runtime: float,
    warn_mbit: float,
    clock: _Clock,
    pinned: bool = False,
    choose: Callable[[Release, list[TorrFile]], TorrFile] = _largest,
) -> tuple[int, TorrFile, Media]:
    """Прогреть релиз, прочитать поток и убедиться, что видео действительно H.264.

    Имя раздачи о кодеке чаще молчит, а видео мы отдаём ``copy`` — ресивер получит ровно
    то, что лежит внутри. Оказалось не h264 — честная строка и следующий кандидат, не
    больше :data:`MAX_TRIES` попыток (§1: молчаливых подмен не бывает).

    ``pinned`` — релиз назван явно (``--release N``): такой неприкосновенен. Кодек всё
    равно проверяется, но вместо подмены выходит громкое предупреждение и показ идёт,
    как просили — иначе флаг для скриптов ничего не гарантирует.
    """
    others = enumerate(ranked, start=1)
    queue = [number]
    if not pinned:
        queue += [n for n, r in others if n != number and is_candidate(r, runtime, warn_mbit)]
    tried: list[str] = []
    for attempt, current in enumerate(queue[:MAX_TRIES], start=1):
        print()
        print("Дорожки: читаю поток…" if attempt == 1 else f"релиз №{current}: читаю поток…")
        # §3.1: magnet уходит в TorrServer и набирает пиров, пока читаются метаданные.
        release = ranked[current - 1]
        torrent_hash = torrserver.warm(release.magnet).result()
        metadata = clock.lap()
        # Фильму — самый крупный файл, сериалу — файл нужной серии (§2.4).
        video = choose(release, torrserver.wait_files(torrent_hash))
        source = torrserver.stream_url(torrent_hash, video.index)
        media = probe(source)
        if (media.video or "h264") == "h264" or pinned:
            if warning := media.video_warning:  # явный релиз играем, но молча — не смеем
                print(warning)
            print(f"(метаданные {metadata}, ffprobe {clock.lap()})")
            return current, video, media
        tried.append(f"№{current} — {media.video}")
        torrserver.drop(torrent_hash)
        following = queue[attempt] if attempt < min(len(queue), MAX_TRIES) else None
        if following is None:
            break
        print(f"релиз №{current} оказался {media.video} — беру №{following}")
    raise NotFoundError(
        f"H.264 не нашёлся ({'; '.join(tried)}): ресивер такое видео может не взять, "
        "а перекодировать мы его не будем — выбери релиз руками: cast <запрос> --release N"
    )


def _resume(config: Config, key: str, entry: Entry, clock: _Clock, dry: bool = False) -> int:
    """Возобновление §2.3: один вопрос и сразу показ. Релиз, файл и дорожка берутся из
    состояния — ни поиска, ни меню, поэтому старт укладывается в 5–15 с (§3.1).
    """
    question = f"«{entry.title}» остановились на {_hms(entry.pos)}. Продолжить? [Да/сначала]"
    answer = _ask_line(question)
    if answer[:1] in {"с", "s", "н", "n"}:  # «сначала» / «с начала» / «нет»
        entry.pos = 0.0
    return _launch(config, key, entry, _about(entry), clock, dry)


def _launch(
    config: Config, key: str, entry: Entry, about: str, clock: _Clock, dry: bool = False
) -> int:
    """Показ уезжает в transient-юнит: ``cast`` завершился — показ продолжается (§3)."""
    if dry:
        print(f"▶ (--dry) {about} — каста нет")
        return EXIT_OK
    # Сначала гасим прошлый показ и только потом пишем свою запись: умирающий юнит по
    # SIGTERM дописывает СВОЮ позицию, и записанный раньше прыжок на s1e5 он бы затёр.
    stop_play_unit()
    state = State.load()
    state.put(key, entry)
    state.save()
    start_play_unit(key)
    _await_playing(config)
    print()
    print(f"▶ {about} → ТВ   (старт {clock.total:.0f} с)")
    return EXIT_OK


def _await_playing(config: Config, timeout: float = 120.0) -> None:
    """Дождаться живой картинки: юнит поднялся и в манифесте есть сегменты. Юнит умер по
    дороге — честная строка из journald, а не «запустил и ушёл» (§1, §5).
    """
    manifest = Path(config.hls_dir) / "index.m3u8"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.suppress(OSError):
            if ".ts" in manifest.read_text(encoding="utf-8"):
                return
        if not unit_active():
            raise InfraError(f"показ не запустился: {unit_why()}")
        time.sleep(0.5)
    stop_play_unit()
    raise InfraError(f"показ не начался за {timeout:.0f} с — {unit_why()}")


def _play(
    config: Config,
    source: str,
    audio: int,
    about: str,
    clock: _Clock,
    watch: Watch | None = None,
) -> int:
    """Упаковка → https-раздача → приёмник (§3). Своих демонов нет: и ffmpeg, и раздача
    живут ровно на время показа и гасятся вместе с ним, что бы ни случилось.
    """
    from torrcast.stream import HlsServer, ffmpeg_hls_command, hls_dir

    out = hls_dir(config.hls_dir)
    start = watch.offset if watch else 0.0
    command = ffmpeg_hls_command(source, audio, str(out), start, config.hls_readrate)
    server = HlsServer(out, config.hls_cert, config.hls_key, port=config.hls_port)
    receiver = make_receiver(config.receiver, config.tv or "", config.hls_cert)
    packer = Packer.start(command, out, config.hls_window)
    try:
        server.start()
        packer.manifest()
        receiver.play(f"{config.hls_base_url.rstrip('/')}/index.m3u8", about)
        print(f"▶ {about} → ТВ   (старт {clock.total:.0f} с)", flush=True)
        _hold(receiver, packer, watch)
    finally:
        with contextlib.suppress(TorrcastError):
            receiver.stop()
        packer.stop()
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


def _hold(receiver: Receiver, packer: Packer, watch: Watch | None = None) -> None:
    """Держим показ: упаковка должна быть жива, не должна убегать от приёмника дальше
    половины окна, из RAM уходит только пройденное, а сторож раз в 10 с пишет позицию.
    """
    while True:
        code = packer.poll()
        if code not in (None, 0):
            # Убитый сигналом ffmpeg ничего сказать не успевает — не выдумываем за него.
            why = f"убит сигналом {-code}" if code < 0 else packer.why()
            raise InfraError(f"упаковка оборвалась: {why}")
        try:
            position = receiver.position()
        except InfraError:  # приёмник позицию не отдаёт — ведём показ по упаковке
            if code == 0:
                return
            packer.prune()  # без позиции остаётся запасное окно в штуках
        else:
            if watch is not None:
                watch.see(position.pos)
                if watch.done and watch.entry.kind == "tv":
                    return  # серия досмотрена — освобождаем показ под следующую (§2.4)
            if not position.playing:
                return
            packer.pace(position.dur - position.pos)
            packer.prune(position.pos)
        time.sleep(2.0)


def _pick_picture(pictures: list[Picture]) -> Picture:
    """Меню франшизы §2.1; один вариант (в том числе после номера) — без вопроса."""
    if len(pictures) == 1:
        print(f"  1. {pictures[0].title} ({pictures[0].year or '?'})")
        return pictures[0]
    print()
    for number, item in enumerate(pictures, start=1):
        kind = ", сериал" if item.kind == "tv" else ""
        print(f"  {number}. {item.title} ({item.year or '?'}{kind})")
    return pictures[_ask("Что смотрим?", len(pictures)) - 1]


def warned(release: Release, runtime: float, warn_mbit: float) -> str:
    """Пометки релиза: HEVC ресивер может не потянуть, жирный битрейт — тоже (§3)."""
    marks = "⚠" if release.is_hevc else ""
    return marks + ("⚠" if bitrate_of(release, runtime) > warn_mbit else "")


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
    """Таблица релизов §2.1: № · качество · размер · сиды · озвучка · кодек. Битрейт для ⚠
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


def _ask_release(ranked: list[Release], args: Args) -> int:
    """Номер релиза: ``--release N`` в обход меню, один вариант — без вопроса."""
    if args.release is not None:
        if not 1 <= args.release <= len(ranked):
            raise NotFoundError(f"релизов {len(ranked)}, номера {args.release} нет")
        return args.release
    return 1 if len(ranked) == 1 else _ask("Какой берём?", len(ranked))


def _ask_audio(media: Media, args: Args) -> int:
    """Выбор дорожки: одна дорожка — вопроса нет, дефолт — русская (§2.1)."""
    if not media.tracks:
        raise InfraError("в файле нет звуковых дорожек")
    labels = "  ".join(f"{t.index + 1}. {t.label}" for t in media.tracks)
    print(f"Дорожки: {labels}")
    if args.audio is not None:
        if not 1 <= args.audio <= len(media.tracks):
            raise NotFoundError(f"дорожек {len(media.tracks)}, номера {args.audio} нет")
        return args.audio - 1
    if len(media.tracks) == 1:
        return 0
    return _ask("Озвучка?", len(media.tracks), default=media.default_track() + 1) - 1


def _ask_line(question: str) -> str:
    """Свободный ответ; Enter и отсутствие терминала — пустая строка, то есть дефолт."""
    try:
        return input(f"{question}: ").strip().casefold()
    except EOFError:
        return ""


def _ask(question: str, count: int, default: int = 1) -> int:
    """Вопрос с дефолтом в скобках: Enter = разумный выбор (§2.1)."""
    while True:
        answer = _ask_line(f"{question} [{default}]")
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= count:
            return int(answer)
        print(f"нужен номер от 1 до {count}")


def _gb(size: int) -> str:
    return f"{size / 1024**3:.1f} ГБ" if size else "—"


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _pad(text: str, width: int) -> str:
    # Ширина колонки считается в знакоместах: ⚠ и подобные занимают ровно одно.
    return text + " " * (width - len(text))


def _hms(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


if __name__ == "__main__":
    raise SystemExit(main())
