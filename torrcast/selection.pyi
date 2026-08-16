"""Типы совместимого фасада отбора."""

from typing import Any

from torrcast.domain.picture import Picture
from torrcast.domain.release import Release

class _Plan:
    picture: Picture
    ranked: list[Release]
    runtime: float
    warn_mbit: float
    series: Any
    recode_at: float
    hard_mbit: float
    loose: bool
    last_resort: bool
    copy_hevc: bool
    kin: list[Picture]
    asked_series: bool
    runtime_known: bool
    off_season: int
    late: Any
    want: Any
    skipped: Any
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def candidates(self, *args: Any, **kwargs: Any) -> Any: ...

def __getattr__(name: str) -> Any: ...
def _continue(*args: Any, **kwargs: Any) -> int | None: ...
