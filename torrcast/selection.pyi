"""Типы совместимого фасада отбора: имена берутся у самого сценария, а не копией."""

from typing import Any

from torrcast.usecases.select import _continue as _continue
from torrcast.usecases.select import _Plan as _Plan
from torrcast.usecases.select import _Prep as _Prep

def __getattr__(name: str) -> Any: ...
