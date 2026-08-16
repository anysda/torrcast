"""Совместимый фасад правил эпизодов и разбора имени релиза."""

from __future__ import annotations

from torrcast.domain.episode_file import EpisodeFile
from torrcast.domain.file_like import FileLike
from torrcast.domain.map_episodes import map_episodes
from torrcast.domain.parse_episode import parse_episode
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.split_episode import split_episode

__all__ = [
    "EpisodeFile",
    "FileLike",
    "map_episodes",
    "parse_episode",
    "parse_release_name",
    "split_episode",
]
