"""Часть CLI; публичный фасад - :mod:`torrcast.cli`.

Реэкспорт меню франшизы: вес картины, дефолт, честные строки про смену картины и отбор
релиза с уходом к дублёру. Ни строчки логики - каждая единица живёт в своём файле.
"""

from __future__ import annotations

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.outside_numbering import outside_numbering
from torrcast.domain.picture import Picture
from torrcast.domain.profile import Profile
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.usecases.choice._ctl import _ctl, _Revivable, _Steerable
from torrcast.usecases.choice._named import _BLURB_INDENT, _named
from torrcast.usecases.choice._namesake import _namesake
from torrcast.usecases.choice._passport import _Passport, _passport
from torrcast.usecases.choice._pick_plan import _pick_plan
from torrcast.usecases.choice._played import _played
from torrcast.usecases.choice.alive_numbers import alive_numbers
from torrcast.usecases.choice.asked_kind import asked_kind
from torrcast.usecases.choice.backed import _rival, backed
from torrcast.usecases.choice.configure import configure
from torrcast.usecases.choice.default_line import default_line
from torrcast.usecases.choice.default_note import _passed_why, default_note
from torrcast.usecases.choice.first_alive import _first_alive, first_alive
from torrcast.usecases.choice.fitness import fitness
from torrcast.usecases.choice.last_hope_note import last_hope_note
from torrcast.usecases.choice.liveliest import liveliest
from torrcast.usecases.choice.liveliness import liveliness
from torrcast.usecases.choice.menu_lines import menu_lines
from torrcast.usecases.choice.namesake_note import namesake_note
from torrcast.usecases.choice.part_one_swap import part_one_swap
from torrcast.usecases.choice.playable import _same_name, playable
from torrcast.usecases.choice.swap_note import _is_default, swap_note
from torrcast.usecases.choice.understudy import understudy
from torrcast.usecases.choice.understudy_note import _why_refused, understudy_note
from torrcast.usecases.choice.warm_order import warm_order
from torrcast.usecases.choice.warned import warned
from torrcast.usecases.choice.year_note import year_note

__all__ = [
    "_BLURB_INDENT",
    "Picture",
    "Profile",
    "Release",
    "_Passport",
    "_Revivable",
    "_Steerable",
    "_ctl",
    "_first_alive",
    "_is_default",
    "_named",
    "_namesake",
    "_passed_why",
    "_passport",
    "_pick_plan",
    "_played",
    "_rival",
    "_same_name",
    "_why_refused",
    "alive_numbers",
    "asked_kind",
    "backed",
    "configure",
    "default_line",
    "default_note",
    "first_alive",
    "fitness",
    "franchise_key",
    "last_hope_note",
    "liveliest",
    "liveliness",
    "menu_lines",
    "namesake_note",
    "outside_numbering",
    "part_one_swap",
    "playable",
    "slugify",
    "split_franchise_index",
    "swap_note",
    "understudy",
    "understudy_note",
    "warm_order",
    "warned",
    "year_note",
]
