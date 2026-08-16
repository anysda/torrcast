"""Совместимый фасад стенда отбора для старых импортов."""
# mypy: ignore-errors

import sys

from torrcast.usecases import select_bench as _selection_bench_impl
from torrcast.usecases.select_bench import _Bench

__all__ = ["_Bench"]

sys.modules[__name__] = _selection_bench_impl
