"""Совместимый фасад разбора имён, эпизодов и франшиз."""

from __future__ import annotations

# Статический список нужен mypy для реэкспортов; внизу сохраняется runtime-список.
__all__ = [
    "THIN_POOL",
    "VIDEO_EXT",
    "_EXTRAS_RE",
    "Episode",
    "EpisodeFile",
    "Kind",
    "Picture",
    "Release",
    "_both_languages",
    "_numbered_line",
    "alt_query",
    "anime_indexer",
    "by_majority",
    "catalog_has_name",
    "cluster",
    "franchise_key",
    "franchise_name",
    "franchises",
    "glue",
    "in_digits",
    "looks_anime",
    "map_episodes",
    "menu_order",
    "other_words",
    "outside_numbering",
    "parse_episode",
    "parse_release_name",
    "part_number",
    "pick_franchise",
    "reads_season",
    "same_word",
    "same_words",
    "seasons_named",
    "slugify",
    "spell",
    "split_episode",
    "split_franchise_index",
    "transliterate",
    "unswap_layout",
    "wire_query",
]

import sys
from types import ModuleType
from typing import Any

from torrcast import catalog as _catalog
from torrcast import episodes as _episodes
from torrcast import franchise as _franchise
from torrcast import parse_name as _parse_name
from torrcast.catalog import (
    _both_languages,
    catalog_has_name,
    pick_franchise,
    reads_season,
)
from torrcast.episodes import (
    EpisodeFile,
    map_episodes,
    parse_episode,
    parse_release_name,
    split_episode,
)
from torrcast.franchise import (
    _numbered_line,
    by_majority,
    cluster,
    franchises,
    glue,
    menu_order,
    other_words,
    outside_numbering,
    seasons_named,
)
from torrcast.parse_name import (
    _EXTRAS_RE,
    THIN_POOL,
    VIDEO_EXT,
    Episode,
    Kind,
    Picture,
    Release,
    alt_query,
    anime_indexer,
    franchise_key,
    franchise_name,
    in_digits,
    looks_anime,
    part_number,
    same_word,
    same_words,
    slugify,
    spell,
    split_franchise_index,
    transliterate,
    unswap_layout,
    wire_query,
)

_PARTS = (_parse_name, _episodes, _franchise, _catalog)
_namespace: dict[str, Any] = {}
for _part in _PARTS:
    _namespace.update(
        (name, value) for name, value in vars(_part).items() if not name.startswith("__")
    )
globals().update(_namespace)
for _part in _PARTS:
    vars(_part).update(_namespace)


class _ParseModule(ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if not name.startswith("__"):
            for part in _PARTS:
                if name in vars(part):
                    setattr(part, name, value)


sys.modules[__name__].__class__ = _ParseModule
__all__ = [name for name in globals() if not name.startswith("_")]
