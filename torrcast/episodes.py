"""Совместимый фасад правил эпизодов и прежнего разбора имени релиза."""

import re

# Разбор release name остаётся в старом слое до отдельного разреза имён.
from torrcast.catalog import (
    _find_year,
    _is_non_video,
    _normalize,
    _normalize_quality,
    _parse_codec,
    _parse_series,
    _parse_source,
    _parse_voices,
    _split_titles,
    _title_zone,
)
from torrcast.domain.episode_file import EpisodeFile
from torrcast.domain.file_like import FileLike
from torrcast.domain.map_episodes import map_episodes
from torrcast.domain.parse_episode import parse_episode
from torrcast.domain.split_episode import split_episode
from torrcast.parse_name import (
    _CYRILLIC,
    _HDR_RE,
    _LATIN,
    _QUALITY_RE,
    Kind,
    Release,
)

__all__ = [
    "EpisodeFile",
    "FileLike",
    "map_episodes",
    "parse_episode",
    "parse_release_name",
    "split_episode",
]


def _bare_episode_span(zone: str) -> tuple[int, ...]:
    match = re.search(r"^(.+?)\s+1\s*-\s*(\d{1,3})\s*$", zone)
    if not match or len(re.findall(r"[A-Za-z]+", match.group(1))) < 3:
        return ()
    end = int(match.group(2))
    return tuple(range(1, end + 1)) if 3 <= end <= 500 else ()


def _parse_release_name(name: str) -> Release:
    """Разобрать имя раздачи; временно остаётся правилом старого слоя."""
    text = _normalize(name)
    year, span = _find_year(text)
    zone, collection = _title_zone(text, span)
    bare_episodes = _bare_episode_span(zone)
    if bare_episodes:
        zone = re.sub(r"\s+1\s*-\s*\d{1,3}\s*$", "", zone)
    title, original, aliases = _split_titles(zone)
    names = (title, *((original,) if original else ()), *aliases)
    latin_names = sum(bool(_LATIN.search(part) and not _CYRILLIC.search(part)) for part in names)
    russian_names = sum(bool(_CYRILLIC.search(part)) for part in names)
    collection = collection or (latin_names >= 3 and russian_names >= 3)
    quality_match = _QUALITY_RE.search(text)
    quality = _normalize_quality(quality_match.group(1)) if quality_match else None
    season, episode, seasons, episodes, series = _parse_series(text)
    if bare_episodes and not episodes:
        episodes, series = bare_episodes, True
    kind: Kind = "other" if _is_non_video(text) else ("tv" if series else "movie")
    return Release(
        raw_name=name,
        title=title,
        original=original,
        aliases=aliases,
        year=year,
        quality=quality,
        codec=_parse_codec(text),
        source=_parse_source(text),
        hdr=bool(_HDR_RE.search(text)),
        voices=_parse_voices(text),
        season=season,
        episode=episode,
        seasons=seasons,
        episodes=episodes,
        kind=kind,
        collection=collection,
    )


parse_release_name = _parse_release_name
