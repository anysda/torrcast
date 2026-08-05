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
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from torrcast import InfraError, NotFoundError, TorrcastError, __version__
from torrcast.cast import Receiver, make_receiver
from torrcast.parse import Episode, Picture, Release, parse_episode, split_franchise_index
from torrcast.search import Prowlarr, to_releases
from torrcast.state import Config, State, load_config, save_config
from torrcast.stream import Media, Packer, bitrate_mbit, stop_play_unit

__all__ = ["Args", "bitrate_of", "main", "parse_args", "rank_releases", "render_table"]

EXIT_OK, EXIT_NOT_FOUND, EXIT_INFRA = 0, 1, 2
#: Сколько строк таблицы релизов показываем: ниже начинаются раздачи без сидов.
TABLE_LIMIT = 12
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

    @property
    def command(self) -> str:
        """``stop`` / ``status`` / ``play`` / ``configure``."""
        if self.query and self.query[0] in {"stop", "status"}:
            return self.query[0]
        if not self.query:
            return "configure" if self.tv else "status"
        return "play"

    @property
    def episode(self) -> Episode | None:
        """Явно указанная серия: ``cast киберпанк s2e5`` (§2.4)."""
        return parse_episode(" ".join(self.query))

    @property
    def title_query(self) -> str:
        """Запрос без хвоста ``sNeM``."""
        text = " ".join(self.query)
        found = self.episode
        return text[: text.lower().find(f"s{found.season}")].strip() if found else text.strip()


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
    """``cast stop`` — снять каст и зафиксировать позицию (§2.5)."""
    config = load_config()
    receiver = make_receiver(config.receiver, config.tv or "")
    with contextlib.suppress(TorrcastError):  # TODO(этап 3): записать позицию в state
        _ = receiver.position()
    receiver.stop()
    stop_play_unit()
    print("остановлено")
    return EXIT_OK


def _cmd_status() -> int:
    """``cast status`` — что играет, позиция/длительность, источник (§2.5)."""
    active = [(key, entry) for key, entry in State.load() if entry.pos > 0]
    if not active:
        print("ничего не играет")
        return EXIT_OK
    key, entry = max(active, key=lambda item: item[1].updated)  # самая свежая запись
    print(f"{entry.title} — {_hms(entry.pos)} / {_hms(entry.dur)} · {key}")
    return EXIT_OK


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
    from torrcast.stream import RUNTIME_GUESS, TorrServer, pick_video_file, probe

    clock = _Clock()
    config = load_config()
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
    runtime = RUNTIME_GUESS.get(picture.kind, 7200.0)
    ranked = rank_releases(picture.releases)

    print()
    print(render_table(ranked, runtime, config.bitrate_warn_mbit))
    release = _ask_release(ranked, args)

    # §3.1: топ-релиз уходит в TorrServer прямо сейчас, меню отвечает поверх прогрева.
    torrserver = TorrServer(config.torrserver_url)
    warm = torrserver.warm(release.magnet)

    print()
    print("Дорожки: читаю поток…")
    torrent_hash = warm.result()
    files = torrserver.wait_files(torrent_hash)
    video = pick_video_file(files)
    source = torrserver.stream_url(torrent_hash, video.index)
    metadata = clock.lap()
    media = probe(source)
    audio = _ask_audio(media, args)

    peak = bitrate_of(release, media.duration or runtime)
    label = media.tracks[audio].label if audio < len(media.tracks) else "—"
    about = f"«{picture.title}» ({picture.year or '?'}) · {release.quality or '?'} · {label}"
    print()
    codec = media.video or "?"
    print(
        f"Файл: {video.name} · {_gb(video.size)} · {_hms(media.duration)} · "
        f"{codec} · ~{peak:.1f} Мбит/с"
    )
    print(f"(метаданные {metadata}, ffprobe {clock.lap()})")
    if media.video_warning:  # молча кастить то, что ресивер не переварит, мы не будем (§1)
        print(media.video_warning)
    if args.dry:
        print(f"▶ (--dry) {about} — каста нет")
        return EXIT_OK
    return _play(config, source, audio, about, clock)


def _play(config: Config, source: str, audio: int, about: str, clock: _Clock) -> int:
    """Упаковка → https-раздача → приёмник (§3). Своих демонов нет: и ffmpeg, и раздача
    живут ровно на время показа и гасятся вместе с ним, что бы ни случилось.
    """
    from torrcast.stream import HlsServer, ffmpeg_hls_command, hls_dir

    out = hls_dir(config.hls_dir)
    command = ffmpeg_hls_command(source, audio, str(out), readrate=config.hls_readrate)
    server = HlsServer(out, config.hls_cert, config.hls_key, port=config.hls_port)
    receiver = make_receiver(config.receiver, config.tv or "", config.hls_cert)
    packer = Packer.start(command, out, config.hls_window)
    try:
        server.start()
        packer.manifest()
        receiver.play(f"{config.hls_base_url.rstrip('/')}/index.m3u8", about)
        print(f"▶ {about} → ТВ   (старт {clock.total:.0f} с)")
        _hold(receiver, packer)
    finally:
        with contextlib.suppress(TorrcastError):
            receiver.stop()
        packer.stop()
        server.stop()

    report = getattr(receiver, "report", None)
    if report is None:
        return EXIT_OK
    print(report.line())
    if not report.ok:
        raise InfraError("приёмник не досмотрел поток — цифры выше")
    return EXIT_OK


def _hold(receiver: Receiver, packer: Packer) -> None:
    """Держим показ: упаковка должна быть жива, не должна убегать от приёмника дальше
    половины окна, а из RAM уходит только то, что приёмник уже прошёл.
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


def rank_releases(releases: list[Release]) -> list[Release]:
    """Порядок меню (§2.1, §3). Дефолт — самый обсиженный релиз первого сорта (H.264,
    известное качество ≥720p); таких нет — просто самый обсиженный. Образы дисков вниз
    всегда: цельного файла внутри нет, стримить нечего.
    """
    return sorted(releases, key=lambda r: (is_disc(r), not r.prime, -r.seeders, -r.size))


def bitrate_of(release: Release, duration: float) -> float:
    return bitrate_mbit(release.size, duration)


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


def _ask_release(ranked: list[Release], args: Args) -> Release:
    """Выбор релиза: ``--release N`` в обход меню, один вариант — без вопроса."""
    if args.release is not None:
        if not 1 <= args.release <= len(ranked):
            raise NotFoundError(f"релизов {len(ranked)}, номера {args.release} нет")
        return ranked[args.release - 1]
    return ranked[0] if len(ranked) == 1 else ranked[_ask("Какой берём?", len(ranked)) - 1]


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


def _ask(question: str, count: int, default: int = 1) -> int:
    """Вопрос с дефолтом в скобках: Enter = разумный выбор (§2.1)."""
    while True:
        try:
            answer = input(f"{question} [{default}]: ").strip()
        except EOFError:
            answer = ""
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
