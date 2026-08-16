"""Совместимый фасад моделей и строковых правил разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data import (
    _CHANNEL_RE,
    _ENDING,
    _FRANCHISE_MIN,
    _GLUE,
    _LAYOUT,
    _NUMERALS,
    _NUMERO_RE,
    _SPELL_X,
    _STEM,
    _TITLE_NUMBER_RE,
    _TRANSLIT,
    THIN_POOL,
)
from torrcast.domain.akin import _akin
from torrcast.domain.alt_query import alt_query
from torrcast.domain.episode import Episode
from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.franchise_name import franchise_name
from torrcast.domain.in_digits import in_digits
from torrcast.domain.paired import _paired
from torrcast.domain.part_number import part_number
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.same_word import same_word
from torrcast.domain.same_words import same_words
from torrcast.domain.slugify import slugify
from torrcast.domain.spell import spell
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.domain.transliterate import transliterate
from torrcast.domain.unbranded import _unbranded
from torrcast.domain.unswap_layout import unswap_layout
from torrcast.domain.wire_query import wire_query

__all__ = [
    "THIN_POOL",
    "_CHANNEL_RE",
    "_ENDING",
    "_FRANCHISE_MIN",
    "_GLUE",
    "_LAYOUT",
    "_NUMERALS",
    "_NUMERO_RE",
    "_SPELL_X",
    "_STEM",
    "_TITLE_NUMBER_RE",
    "_TRANSLIT",
    "Episode",
    "Picture",
    "Release",
    "_akin",
    "_paired",
    "_unbranded",
    "alt_query",
    "franchise_key",
    "franchise_name",
    "in_digits",
    "part_number",
    "same_word",
    "same_words",
    "slugify",
    "spell",
    "split_franchise_index",
    "transliterate",
    "unswap_layout",
    "wire_query",
]
