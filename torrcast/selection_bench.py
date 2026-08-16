"""Совместимый фасад стенда отбора для старых импортов."""

import sys

from torrcast import _selection_bench_impl
from torrcast._selection_bench_impl import _Bench

__all__ = ["_Bench"]

sys.modules[__name__] = _selection_bench_impl
