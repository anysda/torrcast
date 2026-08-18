"""Совместимый фасад разбора имён, эпизодов и франшиз."""

from __future__ import annotations

# Статический список реэкспортов: и mypy, и человек читают его, а не собранный на лету.
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

from torrcast.domain._name_data import (
    _EXTRAS_RE,
    THIN_POOL,
    VIDEO_EXT,
)
from torrcast.domain.alt_query import alt_query
from torrcast.domain.anime_indexer import anime_indexer
from torrcast.domain.both_languages import _both_languages
from torrcast.domain.by_majority import by_majority
from torrcast.domain.catalog_has_name import catalog_has_name
from torrcast.domain.cluster import cluster
from torrcast.domain.episode import Episode
from torrcast.domain.episode_file import EpisodeFile
from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.franchise_name import franchise_name
from torrcast.domain.franchises import franchises
from torrcast.domain.glue import glue
from torrcast.domain.in_digits import in_digits
from torrcast.domain.kind import Kind
from torrcast.domain.looks_anime import looks_anime
from torrcast.domain.map_episodes import map_episodes
from torrcast.domain.menu_order import menu_order
from torrcast.domain.numbered_line import _numbered_line
from torrcast.domain.other_words import other_words
from torrcast.domain.outside_numbering import outside_numbering
from torrcast.domain.parse_episode import parse_episode
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.part_number import part_number
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.domain.reads_season import reads_season
from torrcast.domain.release import Release
from torrcast.domain.same_word import same_word
from torrcast.domain.same_words import same_words
from torrcast.domain.seasons_named import seasons_named
from torrcast.domain.slugify import slugify
from torrcast.domain.spell import spell
from torrcast.domain.split_episode import split_episode
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.domain.transliterate import transliterate
from torrcast.domain.unswap_layout import unswap_layout
from torrcast.domain.wire_query import wire_query
