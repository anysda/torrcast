"""Правило parse series; используют модели и фасады разбора имён."""

from __future__ import annotations

import re

from torrcast.domain._name_data import (
    _CODEC_TOKEN_RE,
    _SEASON_EPISODE_RES,
    _SEASON_ONLY_RES,
    _SERIES_HINT_RE,
)
from torrcast.domain.episode import Episode
from torrcast.domain.episode_span import _episode_span
from torrcast.domain.fansub_episode import _fansub_episode
from torrcast.domain.season_span import _season_span


def _parse_series(
    text: str,
) -> tuple[int | None, int | None, tuple[int, ...], tuple[int, ...], bool]:
    fansub = _fansub_episode(text)
    text = _CODEC_TOKEN_RE.sub(" ", text)
    seasons = _season_span(text)
    episodes = _episode_span(text)
    if seasons:
        return (seasons[0], None, seasons, episodes, True)
    found = _parse_episode(text)
    if found is not None:
        pack = re.search("[eхx]\\s*\\d{1,3}\\s*-\\s*\\d{1,3}", text, re.IGNORECASE)
        years = [int(year) for year in re.findall("\\b(?:19|20)\\d{2}\\b", text)]
        linear = bool(
            pack
            and found.season == 1
            and (len(episodes) > 24)
            and years
            and (max(years) - min(years) >= 2)
        )
        return (
            None if linear else found.season,
            None if pack else found.episode,
            (),
            episodes,
            True,
        )
    number = int(fansub.group("episode")) if fansub else None
    for pattern in _SEASON_ONLY_RES:
        match = pattern.search(text)
        if match:
            return (int(match.group("season")), number, (), episodes, True)
    if number is not None:
        return (None, number, (), episodes, True)
    return (None, None, (), episodes, bool(episodes) or bool(_SERIES_HINT_RE.search(text)))


def _parse_episode(text: str) -> Episode | None:
    for pattern in _SEASON_EPISODE_RES:
        match = pattern.search(text)
        if match:
            return Episode(int(match.group("season")), int(match.group("episode")))
    return None


__all__ = ["_parse_series"]
