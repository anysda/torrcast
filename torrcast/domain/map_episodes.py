"""Сопоставляет видеофайлы торрент-раздачи с эпизодами сериала."""

import re
import statistics
from collections.abc import Callable, Sequence
from typing import Final

from torrcast.domain.episode_file import EpisodeFile
from torrcast.domain.file_like import FileLike
from torrcast.domain.parse_episode import parse_episode
from torrcast.domain.season_numbering import season_numbering

__all__ = ["map_episodes"]

_VIDEO_EXT: Final = (".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".webm", ".m4v", ".mpg")
_JUNK_RE: Final = re.compile(
    r"\b(?:samples?|trailers?|трейлер\w*|teasers?|creditless|nc-?(?:op|ed)|extras?|"
    r"bonus\w*|бонус\w*|specials?|скриншот\w*|screens?|proof|обложк\w*)\b|"
    r"\bop\s*-\s*ed\b|[/\\](?:openings?|endings?|op|ed)[/\\]",
    re.IGNORECASE,
)
_BRACKETS_RE: Final = re.compile(r"[\[(][^\[\]()]*[\])]")
_TECH_TOKEN_RE: Final = re.compile(
    r"^(?:\d{3,4}[xх]\d{3,4}|(?:19|20)\d{2}|\d+bit|\d+fps|\d+кбит|\d+kbps|v\d)$", re.I
)
_RESOLUTIONS: Final = frozenset({"1080", "1440", "2160", "4320"})
_EPISODE_ONLY_RES: Final = (
    re.compile(r"\bep?\.?\s?(?P<episode>\d{1,3})\b(?!\s*(?:сезон|мин))", re.I),
    re.compile(r"\b(?P<episode>\d{1,3})\s*(?:из|of)\s*\d{1,3}\b", re.I),
    re.compile(r"\b(?P<episode>\d{1,3})\s*-?\s*(?:я|ая)?\s*сери", re.I),
    # «Интерны. Серия №181» без сезона: номер после слова, со знаком номера.
    re.compile(r"\bсерия\s*№\s*(?P<episode>\d{1,4})\b", re.I),
)
_SEASON_ONLY_RES: Final = (
    re.compile(r"\bs\s?(?P<season>\d{1,2})\b(?!\s?e)", re.I),
    re.compile(r"(?P<season>\d{1,2})[-\s]*(?:й\s*)?сезон", re.I),
    re.compile(r"season\s*(?P<season>\d{1,2})", re.I),
)


def map_episodes(
    files: Sequence[FileLike],
    season_hint: int | None = None,
    *,
    explicit_only: bool = False,
    by_order: bool = True,
) -> list[EpisodeFile]:
    """Распознать серии, проверяя связность номеров и отбрасывая мусор.

    ``by_order=False`` - без запасной нумерации по порядку файлов: номер, которого не
    назвал ни файл, ни каталог, на вопрос о КОНКРЕТНОЙ серии не отвечает.
    """
    if explicit_only:
        return _map_explicit_episodes(files, season_hint)
    found = _map_numbered_episodes(files, season_hint)
    if found or not by_order:
        return found
    videos = [f for f in files if f.name.lower().endswith(_VIDEO_EXT)]
    videos = _drop_small([f for f in videos if not _JUNK_RE.search(f.name)])
    return _collect(videos, _order_reader(videos), season_hint, strict=False)


def _order_reader(videos: Sequence[FileLike]) -> Callable[[str, int], tuple[int | None, int]]:
    """Номер - место файла; у пака «Season 1/…», «Season 2/…» - место в своём каталоге."""
    seasons = [_folder_season(f.name) for f in videos]
    if None in seasons:
        return _read_order
    ranks = [seasons[:at].count(season) + 1 for at, season in enumerate(seasons)]
    return lambda _name, order: (None, ranks[order - 1])


def _map_numbered_episodes(
    files: Sequence[FileLike], season_hint: int | None = None
) -> list[EpisodeFile]:
    """Распознать только серии, номер которых назван файлом или его каталогом."""
    videos = [f for f in files if f.name.lower().endswith(_VIDEO_EXT)]
    videos = _drop_small([f for f in videos if not _JUNK_RE.search(f.name)])
    for read in (_read_sne, _read_episode_only, _read_bare):
        found = _collect(videos, read, season_hint)
        if found:
            # Сотни как сезон («S01/101 Pilot») читаются только у голых номеров.
            folders = {f.index: _folder_season(f.name) for f in videos if read is _read_bare}
            return season_numbering(found, folders)
    return []


def _map_explicit_episodes(
    files: Sequence[FileLike], season_hint: int | None = None
) -> list[EpisodeFile]:
    """Распознать серии, явно названные как серия, а не одним голым числом."""
    videos = [f for f in files if f.name.lower().endswith(_VIDEO_EXT)]
    videos = _drop_small([f for f in videos if not _JUNK_RE.search(f.name)])
    for read in (_read_sne, _read_episode_only):
        found = _collect(videos, read, season_hint)
        if found:
            return found
    return []


def _collect(
    videos: Sequence[FileLike],
    read: Callable[[str, int], tuple[int | None, int] | None],
    hint: int | None,
    strict: bool = True,
) -> list[EpisodeFile]:
    picked: dict[tuple[int, int], FileLike] = {}
    matched = 0
    for order, item in enumerate(videos, start=1):
        found = read(_base(item.name), order)
        if found is None:
            continue
        matched += 1
        season, episode = found
        season = season if season is not None else _season_of(item.name, hint)
        was = picked.get((season, episode))
        if was is None or item.size > was.size:
            picked[(season, episode)] = item
    if strict and (not picked or len(picked) * 10 < matched * 9 or matched * 2 < len(videos)):
        return []
    return sorted(
        (EpisodeFile(f.index, s, e, _base(f.name), f.size) for (s, e), f in picked.items()),
        key=lambda f: (f.season, f.episode),
    )


def _read_sne(name: str, _order: int) -> tuple[int | None, int] | None:
    found = parse_episode(name)
    return (found.season, found.episode) if found else None


def _read_episode_only(name: str, _order: int) -> tuple[int | None, int] | None:
    for pattern in _EPISODE_ONLY_RES:
        match = pattern.search(name)
        if match:
            return None, int(match.group("episode"))
    return None


def _read_bare(name: str, _order: int) -> tuple[int | None, int] | None:
    bare = _BRACKETS_RE.sub(" ", name)
    tokens = [t for t in re.split(r"[\s._\-]+", bare) if t and not _TECH_TOKEN_RE.match(t)]
    if tokens and tokens[0].isdigit() and len(tokens[0]) == 3:
        # «204 Four Days Out -- 4 дня вне игры»: номер серии стоит первым, в названии своё.
        return None, int(tokens[0])
    numbers = [t for t in tokens if t.isdigit() and len(t) <= 4]
    # Четыре знака - сквозной счёт («One Piece - 1061»), но 1080 рядом с номером - кадр.
    plain = [t for t in numbers if t not in _RESOLUTIONS] or numbers
    return (None, int(plain[-1])) if plain else None


def _read_order(_name: str, order: int) -> tuple[int | None, int]:
    return None, order


def _season_of(path: str, hint: int | None) -> int:
    return _folder_season(path) or hint or 1


def _folder_season(path: str) -> int | None:
    folder = path.rsplit("/", 1)[0] if "/" in path else ""
    for pattern in _SEASON_ONLY_RES:
        match = pattern.search(folder)
        if match:
            return int(match.group("season"))
    return None


def _drop_small(videos: list[FileLike]) -> list[FileLike]:
    sizes = [f.size for f in videos if f.size > 0]
    if len(sizes) < 3:
        return videos
    edge = statistics.median(sizes) * 0.35
    return [f for f in videos if f.size >= edge or f.size == 0]


def _base(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]
