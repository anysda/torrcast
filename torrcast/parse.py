"""Совместимый фасад разбора имён, эпизодов и франшиз."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from torrcast import catalog as _catalog
from torrcast import episodes as _episodes
from torrcast import franchise as _franchise
from torrcast import parse_name as _parse_name
from torrcast.catalog import _both_languages as _both_languages
from torrcast.catalog import (
    catalog_has_name as catalog_has_name,
)
from torrcast.catalog import (
    pick_franchise as pick_franchise,
)
from torrcast.catalog import (
    reads_season as reads_season,
)
from torrcast.episodes import (
    EpisodeFile as EpisodeFile,
)
from torrcast.episodes import (
    map_episodes as map_episodes,
)
from torrcast.episodes import (
    parse_episode as parse_episode,
)
from torrcast.episodes import (
    parse_release_name as parse_release_name,
)
from torrcast.episodes import split_episode as split_episode
from torrcast.franchise import _numbered_line as _numbered_line
from torrcast.franchise import (
    by_majority as by_majority,
)
from torrcast.franchise import (
    cluster as cluster,
)
from torrcast.franchise import (
    franchises as franchises,
)
from torrcast.franchise import (
    glue as glue,
)
from torrcast.franchise import (
    menu_order as menu_order,
)
from torrcast.franchise import other_words as other_words
from torrcast.franchise import (
    outside_numbering as outside_numbering,
)
from torrcast.franchise import (
    seasons_named as seasons_named,
)
from torrcast.parse_name import _EXTRAS_RE as _EXTRAS_RE
from torrcast.parse_name import (
    THIN_POOL as THIN_POOL,
)
from torrcast.parse_name import (
    VIDEO_EXT as VIDEO_EXT,
)
from torrcast.parse_name import (
    Episode as Episode,
)
from torrcast.parse_name import Kind as Kind
from torrcast.parse_name import (
    Picture as Picture,
)
from torrcast.parse_name import (
    Release as Release,
)
from torrcast.parse_name import (
    alt_query as alt_query,
)
from torrcast.parse_name import (
    anime_indexer as anime_indexer,
)
from torrcast.parse_name import (
    franchise_key as franchise_key,
)
from torrcast.parse_name import (
    franchise_name as franchise_name,
)
from torrcast.parse_name import (
    in_digits as in_digits,
)
from torrcast.parse_name import (
    looks_anime as looks_anime,
)
from torrcast.parse_name import (
    part_number as part_number,
)
from torrcast.parse_name import (
    same_word as same_word,
)
from torrcast.parse_name import (
    same_words as same_words,
)
from torrcast.parse_name import (
    slugify as slugify,
)
from torrcast.parse_name import (
    spell as spell,
)
from torrcast.parse_name import (
    split_franchise_index as split_franchise_index,
)
from torrcast.parse_name import (
    transliterate as transliterate,
)
from torrcast.parse_name import (
    unswap_layout as unswap_layout,
)
from torrcast.parse_name import wire_query as wire_query

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
