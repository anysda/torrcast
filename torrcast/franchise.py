"""Совместимый фасад склейки франшиз."""

from __future__ import annotations

from torrcast.domain.alias_slugs import _alias_slugs
from torrcast.domain.aliases import _aliases
from torrcast.domain.by_majority import by_majority
from torrcast.domain.by_words import _by_words
from torrcast.domain.chapter_of import _chapter_of
from torrcast.domain.cluster import cluster as _cluster
from torrcast.domain.compose import _compose
from torrcast.domain.confirmed_continuations import confirmed_continuations
from torrcast.domain.continued import _continued
from torrcast.domain.franchise_item_key import _franchise_item_key
from torrcast.domain.franchises import franchises
from torrcast.domain.free_first import _free_first
from torrcast.domain.glue import glue
from torrcast.domain.glued_year import _glued_year
from torrcast.domain.group_weight import _group_weight
from torrcast.domain.link import _link
from torrcast.domain.menu_order import menu_order
from torrcast.domain.numbered_line import _numbered_line
from torrcast.domain.other_words import other_words
from torrcast.domain.outside_numbering import outside_numbering
from torrcast.domain.picture import Picture
from torrcast.domain.picture_season_span import _picture_season_span
from torrcast.domain.release import Release
from torrcast.domain.run_span import _run_span
from torrcast.domain.seasons_named import seasons_named
from torrcast.domain.sorted import _sorted
from torrcast.domain.unchaptered import _unchaptered
from torrcast.domain.word_list import _word_list
from torrcast.domain.words import _words

__all__ = [
    "_alias_slugs",
    "_aliases",
    "_by_words",
    "_chapter_of",
    "_compose",
    "_continued",
    "_franchise_item_key",
    "_free_first",
    "_glued_year",
    "_group_weight",
    "_link",
    "_numbered_line",
    "_picture_season_span",
    "_run_span",
    "_sorted",
    "_unchaptered",
    "_word_list",
    "_words",
    "by_majority",
    "cluster",
    "confirmed_continuations",
    "franchises",
    "glue",
    "menu_order",
    "other_words",
    "outside_numbering",
    "seasons_named",
]


def _cluster_facade(releases: list[Release]) -> list[Picture]:
    """Сохраняет наблюдаемость склейки через старый фасад."""
    return _cluster(releases, glue_rule=glue)


cluster = _cluster_facade
