"""Совместимый фасад справки о картинах."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from torrcast import facts_fetch as _fetch
from torrcast import facts_origin as _origin
from torrcast.facts_fetch import (
    BLURB_CAP as BLURB_CAP,
)
from torrcast.facts_fetch import (
    HTTP_TIMEOUT as HTTP_TIMEOUT,
)
from torrcast.facts_fetch import (
    TYPE_CHECKING as TYPE_CHECKING,
)
from torrcast.facts_fetch import Facts as Facts
from torrcast.facts_fetch import (
    Path as Path,
)
from torrcast.facts_fetch import (
    _about_cinema as _about_cinema,
)
from torrcast.facts_fetch import (
    _article as _article,
)
from torrcast.facts_fetch import (
    _cache_path as _cache_path,
)
from torrcast.facts_fetch import (
    _cached as _cached,
)
from torrcast.facts_fetch import (
    _cached_origin as _cached_origin,
)
from torrcast.facts_fetch import (
    _crowded as _crowded,
)
from torrcast.facts_fetch import (
    _ends_phrase as _ends_phrase,
)
from torrcast.facts_fetch import (
    _extract_params as _extract_params,
)
from torrcast.facts_fetch import (
    _fits_type as _fits_type,
)
from torrcast.facts_fetch import (
    _key as _key,
)
from torrcast.facts_fetch import (
    _localized_short_name as _localized_short_name,
)
from torrcast.facts_fetch import (
    _origin_key as _origin_key,
)
from torrcast.facts_fetch import (
    _other_part as _other_part,
)
from torrcast.facts_fetch import (
    _pages as _pages,
)
from torrcast.facts_fetch import (
    _ranked as _ranked,
)
from torrcast.facts_fetch import (
    _read_cache as _read_cache,
)
from torrcast.facts_fetch import (
    _read_pages as _read_pages,
)
from torrcast.facts_fetch import (
    _remember as _remember,
)
from torrcast.facts_fetch import (
    _remember_origin as _remember_origin,
)
from torrcast.facts_fetch import (
    _same_latin as _same_latin,
)
from torrcast.facts_fetch import (
    _search_params as _search_params,
)
from torrcast.facts_fetch import (
    _write_cache as _write_cache,
)
from torrcast.facts_fetch import (
    akin as akin,
)
from torrcast.facts_fetch import (
    english_title as english_title,
)
from torrcast.facts_fetch import (
    fetch as fetch,
)
from torrcast.facts_fetch import (
    json as json,
)
from torrcast.facts_fetch import (
    latin_title as latin_title,
)
from torrcast.facts_fetch import (
    namesake as namesake,
)
from torrcast.facts_fetch import (
    picture_year as picture_year,
)
from torrcast.facts_fetch import (
    ratings as ratings,
)
from torrcast.facts_fetch import (
    re as re,
)
from torrcast.facts_fetch import (
    read_origin as read_origin,
)
from torrcast.facts_fetch import (
    read_sparql as read_sparql,
)
from torrcast.facts_fetch import (
    same_words as same_words,
)
from torrcast.facts_fetch import (
    sentence as sentence,
)
from torrcast.facts_fetch import shorten as shorten
from torrcast.facts_fetch import (
    slugify as slugify,
)
from torrcast.facts_fetch import (
    split_franchise_index as split_franchise_index,
)
from torrcast.facts_fetch import (
    state_path as state_path,
)
from torrcast.facts_fetch import (
    threading as threading,
)
from torrcast.facts_fetch import (
    time as time,
)
from torrcast.facts_fetch import (
    transliterate as transliterate,
)
from torrcast.facts_fetch import (
    wiki_extracts as wiki_extracts,
)
from torrcast.facts_fetch import (
    wikidata_ids as wikidata_ids,
)
from torrcast.facts_origin import (
    _ABBREV as _ABBREV,
)
from torrcast.facts_origin import (
    _CINEMA_RE as _CINEMA_RE,
)
from torrcast.facts_origin import (
    _CJK as _CJK,
)
from torrcast.facts_origin import (
    _CYRILLIC as _CYRILLIC,
)
from torrcast.facts_origin import (
    _DEFAULT_CACHE_PATH as _DEFAULT_CACHE_PATH,
)
from torrcast.facts_origin import (
    _EXCHARS as _EXCHARS,
)
from torrcast.facts_origin import (
    _EXLIMIT as _EXLIMIT,
)
from torrcast.facts_origin import (
    _FILM_WORD_RE as _FILM_WORD_RE,
)
from torrcast.facts_origin import (
    _GENRE_RE as _GENRE_RE,
)
from torrcast.facts_origin import (
    _HATNOTE_RE as _HATNOTE_RE,
)
from torrcast.facts_origin import (
    _LAST_WORD_RE as _LAST_WORD_RE,
)
from torrcast.facts_origin import (
    _MADE_RE as _MADE_RE,
)
from torrcast.facts_origin import (
    _NEAR_LETTERS as _NEAR_LETTERS,
)
from torrcast.facts_origin import (
    _ODD_WEIGHT as _ODD_WEIGHT,
)
from torrcast.facts_origin import (
    _ORIGINAL_RE as _ORIGINAL_RE,
)
from torrcast.facts_origin import (
    _PHRASE_WORDS as _PHRASE_WORDS,
)
from torrcast.facts_origin import (
    _QUALIFIERS as _QUALIFIERS,
)
from torrcast.facts_origin import (
    _RESOLVE_LOCK as _RESOLVE_LOCK,
)
from torrcast.facts_origin import (
    _RESOLVE_TTL as _RESOLVE_TTL,
)
from torrcast.facts_origin import (
    _RESOLVED as _RESOLVED,
)
from torrcast.facts_origin import (
    _RU_LOCK as _RU_LOCK,
)
from torrcast.facts_origin import (
    _RU_NAMES as _RU_NAMES,
)
from torrcast.facts_origin import (
    _RUNTIME_RE as _RUNTIME_RE,
)
from torrcast.facts_origin import (
    _SCREEN_RE as _SCREEN_RE,
)
from torrcast.facts_origin import (
    _SEARCH_HITS as _SEARCH_HITS,
)
from torrcast.facts_origin import (
    _SENTENCE_START_RE as _SENTENCE_START_RE,
)
from torrcast.facts_origin import (
    _SERIES_WORD_RE as _SERIES_WORD_RE,
)
from torrcast.facts_origin import (
    _SUGGEST_HITS as _SUGGEST_HITS,
)
from torrcast.facts_origin import (
    _TAIL_RE as _TAIL_RE,
)
from torrcast.facts_origin import (
    _TITLED_RE as _TITLED_RE,
)
from torrcast.facts_origin import (
    _TV_KINDS as _TV_KINDS,
)
from torrcast.facts_origin import (
    _VOTES as _VOTES,
)
from torrcast.facts_origin import (
    _WIKI_HOST as _WIKI_HOST,
)
from torrcast.facts_origin import (
    _WIKI_PATH as _WIKI_PATH,
)
from torrcast.facts_origin import (
    _WIKIDATA_HOST as _WIKIDATA_HOST,
)
from torrcast.facts_origin import (
    _WIKIDATA_PATH as _WIKIDATA_PATH,
)
from torrcast.facts_origin import (
    _WORK_RE as _WORK_RE,
)
from torrcast.facts_origin import (
    _YEAR_RE as _YEAR_RE,
)
from torrcast.facts_origin import CACHE_PATH as CACHE_PATH
from torrcast.facts_origin import (
    EMPTY_TTL as EMPTY_TTL,
)
from torrcast.facts_origin import FACTS_BUDGET as FACTS_BUDGET
from torrcast.facts_origin import RATINGS_PATH as RATINGS_PATH
from torrcast.facts_origin import (
    RU_NAMES_PATH as RU_NAMES_PATH,
)
from torrcast.facts_origin import (
    TOPUP_LIMIT as TOPUP_LIMIT,
)
from torrcast.facts_origin import (
    USER_AGENT as USER_AGENT,
)
from torrcast.facts_origin import Fact as Fact
from torrcast.facts_origin import (
    Final as Final,
)
from torrcast.facts_origin import Origin as Origin
from torrcast.facts_origin import (
    _asked_otherwise as _asked_otherwise,
)
from torrcast.facts_origin import (
    _by_phrase as _by_phrase,
)
from torrcast.facts_origin import (
    _catalogued as _catalogued,
)
from torrcast.facts_origin import (
    _digit_edit as _digit_edit,
)
from torrcast.facts_origin import (
    _imdb_ru as _imdb_ru,
)
from torrcast.facts_origin import (
    _IPv4Connection as _IPv4Connection,
)
from torrcast.facts_origin import (
    _misremembered as _misremembered,
)
from torrcast.facts_origin import (
    _near_name as _near_name,
)
from torrcast.facts_origin import (
    _one_edit as _one_edit,
)
from torrcast.facts_origin import (
    _origin_typed as _origin_typed,
)
from torrcast.facts_origin import (
    _outweighed as _outweighed,
)
from torrcast.facts_origin import (
    _own_name_first as _own_name_first,
)
from torrcast.facts_origin import (
    _read_ru_names as _read_ru_names,
)
from torrcast.facts_origin import (
    _resolve as _resolve,
)
from torrcast.facts_origin import (
    _ru_names as _ru_names,
)
from torrcast.facts_origin import (
    _RuName as _RuName,
)
from torrcast.facts_origin import (
    _same_picture_origin as _same_picture_origin,
)
from torrcast.facts_origin import (
    _second_source_year as _second_source_year,
)
from torrcast.facts_origin import (
    _suggested as _suggested,
)
from torrcast.facts_origin import (
    _votes as _votes,
)
from torrcast.facts_origin import (
    confirmed_year as confirmed_year,
)
from torrcast.facts_origin import (
    confirms as confirms,
)
from torrcast.facts_origin import (
    contextlib as contextlib,
)
from torrcast.facts_origin import (
    dataclass as dataclass,
)
from torrcast.facts_origin import (
    get_json as get_json,
)
from torrcast.facts_origin import (
    hms as hms,
)
from torrcast.facts_origin import (
    http as http,
)
from torrcast.facts_origin import minutes_of as minutes_of
from torrcast.facts_origin import origin as origin
from torrcast.facts_origin import (
    origin_either as origin_either,
)
from torrcast.facts_origin import (
    origin_now as origin_now,
)
from torrcast.facts_origin import (
    os as os,
)
from torrcast.facts_origin import (
    published_year as published_year,
)
from torrcast.facts_origin import (
    read_published as read_published,
)
from torrcast.facts_origin import (
    redirected_name as redirected_name,
)
from torrcast.facts_origin import same_name as same_name
from torrcast.facts_origin import (
    same_word as same_word,
)
from torrcast.facts_origin import (
    socket as socket,
)
from torrcast.facts_origin import (
    ssl as ssl,
)
from torrcast.facts_origin import titles_for as titles_for
from torrcast.facts_origin import (
    urlencode as urlencode,
)

_PARTS = (_origin, _fetch)
_namespace: dict[str, Any] = {}
for _part in _PARTS:
    _namespace.update(
        (name, value) for name, value in vars(_part).items() if not name.startswith("__")
    )
globals().update(_namespace)
for _part in _PARTS:
    vars(_part).update(_namespace)


class _FactsModule(ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if not name.startswith("__"):
            for part in _PARTS:
                if name in vars(part):
                    setattr(part, name, value)


sys.modules[__name__].__class__ = _FactsModule
__all__ = [name for name in globals() if not name.startswith("_")]
