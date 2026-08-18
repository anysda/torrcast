"""Часть CLI; публичный фасад — :mod:`torrcast.cli`.

Реэкспорт кругов добора: второй заход по потолку, по сезону и по озвучке, план картины
и долив опоздавшего индексера. Ни строчки логики - каждая единица живёт в своём файле.

⚠️ Имена круга поиска (``_ask``, ``_no_budget``, ``_asked_kind``) отсюда не реэкспортятся:
плоскому фасаду их отдаёт сам поиск, а импорт сюда замкнул бы пакеты друг на друга.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, TypeAlias

from torrcast.domain._series import _Series
from torrcast.domain.catalog_has_name import catalog_has_name
from torrcast.domain.episode import Episode
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.minutes_of import minutes_of
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.same_name import same_name
from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.menu_order import menu_order
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.recodes_whole import recodes_whole
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.domain.transliterate import transliterate
from torrcast.ports.journal import journal
from torrcast.ports.passport_source import PassportSource
from torrcast.ports.torrent_catalogue import IndexerClient, RawRow, TorrentCatalogue
from torrcast.usecases.choice import first_alive, fitness
from torrcast.usecases.rank import gate_open, last_hope, rank_releases
from torrcast.usecases.reinforce._as_is import _as_is
from torrcast.usecases.reinforce._ceiling_hides_name import _ceiling_hides_name
from torrcast.usecases.reinforce._ceiling_reinforce import _ceiling_reinforce
from torrcast.usecases.reinforce._foreign_note import KIN_SHOWN, _foreign_note
from torrcast.usecases.reinforce._lacks_season import _lacks_season
from torrcast.usecases.reinforce._leading import _leading
from torrcast.usecases.reinforce._plan_for import _plan_for
from torrcast.usecases.reinforce._season_reinforce import _season_reinforce
from torrcast.usecases.reinforce._timed import _timed
from torrcast.usecases.reinforce._topup import _topup
from torrcast.usecases.reinforce._twin import _twin
from torrcast.usecases.reinforce._voice_reinforce import _voice_reinforce
from torrcast.usecases.reinforce.configure import configure
from torrcast.usecases.reinforce.same_picture import same_picture
from torrcast.usecases.reinforce.voiceless_pool import voiceless_pool

__all__ = [
    "CAUTIOUS",
    "KIN_SHOWN",
    "TYPE_CHECKING",
    "Any",
    "Episode",
    "Fact",
    "IndexerClient",
    "Origin",
    "PassportSource",
    "Picture",
    "Profile",
    "RawRow",
    "Release",
    "TorrentCatalogue",
    "TypeAlias",
    "_Series",
    "_as_is",
    "_ceiling_hides_name",
    "_ceiling_reinforce",
    "_foreign_note",
    "_lacks_season",
    "_leading",
    "_plan_for",
    "_season_reinforce",
    "_timed",
    "_topup",
    "_twin",
    "_voice_reinforce",
    "annotations",
    "catalog_has_name",
    "configure",
    "first_alive",
    "fitness",
    "franchise_key",
    "gate_open",
    "journal",
    "last_hope",
    "menu_order",
    "minutes_of",
    "rank_releases",
    "recodes_whole",
    "replace",
    "same_name",
    "same_picture",
    "slugify",
    "split_franchise_index",
    "transliterate",
    "voiceless_pool",
]
