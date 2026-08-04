"""CLI — единственный наш процесс (§3 ТЗ).

Контракт (§5)::

    cast <запрос> [sNeM] [--new] [--release N] [--audio N] [--dry]
    cast stop
    cast status
    cast --tv <ip>

Коды выхода: ``0`` ок · ``1`` не нашли · ``2`` инфра-ошибка.
Наружу — короткие русские строки, трейсбеков не показываем (§6).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from torrcast import InfraError, NotFoundError, TorrcastError, __version__
from torrcast.cast import make_receiver
from torrcast.parse import Episode, Picture, parse_episode, split_franchise_index
from torrcast.search import Prowlarr, to_releases
from torrcast.state import Config, State, load_config, save_config

__all__ = ["Args", "main", "parse_args"]

EXIT_OK = 0
EXIT_NOT_FOUND = 1
EXIT_INFRA = 2


@dataclass(slots=True)
class Args:
    """Разобранные аргументы командной строки."""

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
    parser = argparse.ArgumentParser(
        prog="cast",
        description="torrcast — найти релиз и кастить его на ТВ без скачивания",
        allow_abbrev=False,
    )
    parser.add_argument("query", nargs="*", help="название, либо stop / status")
    parser.add_argument("--tv", metavar="IP", help="разовая настройка адреса ТВ")
    parser.add_argument("--release", type=int, metavar="N", help="взять релиз N без меню")
    parser.add_argument("--audio", type=int, metavar="N", help="взять дорожку N без меню")
    parser.add_argument("--new", action="store_true", help="забыть прогресс и выбрать заново")
    parser.add_argument("--dry", action="store_true", help="весь резолв без каста")
    parser.add_argument("--version", action="version", version=f"torrcast {__version__}")
    parsed = parser.parse_args(argv)
    return Args(
        query=list(parsed.query),
        tv=parsed.tv,
        release=parsed.release,
        audio=parsed.audio,
        new=parsed.new,
        dry=parsed.dry,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входа console-script ``cast``."""
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
    except InfraError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INFRA
    except TorrcastError as exc:
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
    from torrcast.stream import stop_play_unit

    config = load_config()
    receiver = make_receiver(config.receiver, config.tv or "")
    snapshot = None
    try:
        snapshot = receiver.position()
    except TorrcastError:
        snapshot = None
    receiver.stop()
    stop_play_unit()
    # TODO(этап 3): записать snapshot.pos в state перед выходом.
    _ = snapshot
    print("остановлено")
    return EXIT_OK


def _cmd_status() -> int:
    """``cast status`` — что играет, позиция/длительность, источник (§2.5)."""
    state = State.load()
    active = [(key, entry) for key, entry in state if entry.pos > 0]
    if not active:
        print("ничего не играет")
        return EXIT_OK
    for key, entry in sorted(active, key=lambda item: item[1].updated, reverse=True)[:1]:
        print(f"{entry.title} — {_hms(entry.pos)} / {_hms(entry.dur)} · {key}")
    return EXIT_OK


def _cmd_play(args: Args) -> int:
    """Основной сценарий: запрос → франшиза → релиз → дорожка → каст (§2.1).

    TODO(этап 1): меню франшизы/релизов/дорожек и прогрев топ-релиза под меню.
    TODO(этап 2): упаковка в HLS и передача манифеста приёмнику.
    """
    config = load_config()
    _require_search_config(config)

    name, index = split_franchise_index(args.title_query)
    prowlarr = Prowlarr(config.prowlarr_url, config.prowlarr_apikey)
    releases = to_releases(prowlarr.search(name))

    from torrcast.parse import cluster

    pictures = cluster(releases)
    if not pictures:
        raise NotFoundError(f"по запросу «{name}» ничего не разобралось")

    picture = _pick_franchise(pictures, index, name)
    if args.dry:
        _print_dry(picture)
        return EXIT_OK

    raise InfraError("каст ещё не реализован — пока доступен только --dry")


def _pick_franchise(pictures: list[Picture], index: int | None, name: str) -> Picture:
    """Номер в запросе = позиция во франшизе по году (§2.2).

    Молчаливых подмен нет (§1): если номера столько нет, честно говорим сколько есть.
    """
    if index is None:
        return pictures[0]
    if 1 <= index <= len(pictures):
        return pictures[index - 1]
    raise NotFoundError(f"во франшизе «{name}» {len(pictures)} шт., номера {index} нет")


def _print_dry(picture: Picture) -> None:
    """Печать цепочки резолва для ``--dry`` (приёмка этапа 1)."""
    year = picture.year or "?"
    print(f"{picture.title} ({year}) · {picture.kind} · ключ {picture.key}")
    ranked = sorted(picture.releases, key=lambda r: (r.is_hevc, -r.seeders))
    for number, release in enumerate(ranked, start=1):
        mark = " ⚠" if release.is_hevc else ""
        voices = ", ".join(release.voices) or "—"
        size = f"{release.size / 1024**3:.1f} ГБ" if release.size else "—"
        print(
            f"  {number}. {release.quality or '?':>6}  {size:>8}  "
            f"{release.seeders:>4} сид  {voices}  {release.codec or '?'}{mark}"
        )


def _require_search_config(config: Config) -> None:
    """Без Prowlarr искать нечем — это инфра-ошибка, а не «не нашли»."""
    if not config.prowlarr_apikey:
        raise InfraError("не настроен Prowlarr: apikey пуст, перезапусти ./install.sh")


def _hms(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


if __name__ == "__main__":
    raise SystemExit(main())
