"""Разбирает имя раздачи в :class:`~torrcast.domain.release.Release`."""

from __future__ import annotations

import re

from torrcast.domain._name_data.data_1 import _CYRILLIC, _HDR_RE, _LATIN, _QUALITY_RE
from torrcast.domain.find_year import _find_year
from torrcast.domain.is_non_video import _is_non_video
from torrcast.domain.kind import Kind
from torrcast.domain.normalize import _normalize
from torrcast.domain.normalize_quality import _normalize_quality
from torrcast.domain.parse_codec import _parse_codec
from torrcast.domain.parse_series import _parse_series
from torrcast.domain.parse_source import _parse_source
from torrcast.domain.parse_voices import _parse_voices
from torrcast.domain.release import Release
from torrcast.domain.split_titles import _split_titles
from torrcast.domain.title_zone import _title_zone


def _bare_episode_span(zone: str) -> tuple[int, ...]:
    """Голая линейка «1-N» в хвосте зоны названия: серии без слова «сезон»."""
    match = re.search(r"^(.+?)\s+1\s*-\s*(\d{1,3})\s*$", zone)
    if not match or len(re.findall(r"[A-Za-z]+", match.group(1))) < 3:
        return ()
    end = int(match.group(2))
    return tuple(range(1, end + 1)) if 3 <= end <= 500 else ()


def parse_release_name(name: str) -> Release:
    """Разобрать имя раздачи."""
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
