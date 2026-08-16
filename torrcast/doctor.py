"""Совместимый фасад прежних системных проверок ``cast doctor``."""

import sys

from torrcast import doctor_checks as _implementation
from torrcast.doctor_checks import CAST_PORT, checkup

__all__ = ["CAST_PORT", "checkup"]

sys.modules[__name__] = _implementation
