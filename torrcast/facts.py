"""Совместимый фасад справки о картинах."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from torrcast import facts_fetch as _fetch
from torrcast import facts_origin as _origin
from torrcast.facts_fetch import Facts as Facts
from torrcast.facts_fetch import shorten as shorten
from torrcast.facts_origin import CACHE_PATH as CACHE_PATH
from torrcast.facts_origin import FACTS_BUDGET as FACTS_BUDGET
from torrcast.facts_origin import RATINGS_PATH as RATINGS_PATH
from torrcast.facts_origin import Fact as Fact
from torrcast.facts_origin import Origin as Origin
from torrcast.facts_origin import minutes_of as minutes_of
from torrcast.facts_origin import origin as origin
from torrcast.facts_origin import same_name as same_name
from torrcast.facts_origin import titles_for as titles_for

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
