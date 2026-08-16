"""Совместимый фасад сопоставления раздачи с картиной."""

from __future__ import annotations

from torrcast.domain._name_data import _SUBTITLE_RE
from torrcast.domain.both_languages import _both_languages
from torrcast.domain.both_words import _both_words
from torrcast.domain.by_alias import _by_alias
from torrcast.domain.by_both_names import _by_both_names
from torrcast.domain.by_subtitle import _by_subtitle
from torrcast.domain.catalog_has_name import catalog_has_name
from torrcast.domain.episode_span import _episode_span
from torrcast.domain.fansub_episode import _fansub_episode
from torrcast.domain.find_year import _find_year
from torrcast.domain.is_non_video import _is_non_video
from torrcast.domain.kindred import _kindred
from torrcast.domain.living_part import _living_part
from torrcast.domain.normalize import _normalize
from torrcast.domain.normalize_quality import _normalize_quality
from torrcast.domain.numbered import _numbered
from torrcast.domain.numbered_season import _numbered_season
from torrcast.domain.one_name_is_enough import _one_name_is_enough
from torrcast.domain.parse_codec import _parse_codec
from torrcast.domain.parse_series import _parse_series
from torrcast.domain.parse_source import _parse_source
from torrcast.domain.parse_voices import _parse_voices
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.reads_season import reads_season
from torrcast.domain.season_span import _season_span
from torrcast.domain.split_titles import _split_titles
from torrcast.domain.subtitles import _subtitles
from torrcast.domain.title_zone import _title_zone
from torrcast.domain.with_subtitled import _with_subtitled

__all__ = [
    "_SUBTITLE_RE",
    "_both_languages",
    "_both_words",
    "_by_alias",
    "_by_both_names",
    "_by_subtitle",
    "_episode_span",
    "_fansub_episode",
    "_find_year",
    "_is_non_video",
    "_kindred",
    "_living_part",
    "_normalize",
    "_normalize_quality",
    "_numbered",
    "_numbered_season",
    "_one_name_is_enough",
    "_parse_codec",
    "_parse_series",
    "_parse_source",
    "_parse_voices",
    "_season_span",
    "_split_titles",
    "_subtitles",
    "_title_zone",
    "_with_subtitled",
    "catalog_has_name",
    "pick_franchise",
    "reads_season",
]
