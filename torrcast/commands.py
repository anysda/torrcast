"""Совместимый фасад прежнего модуля CLI."""

import sys

from torrcast import commands_legacy as _implementation
from torrcast.commands_legacy import Args, main, parse_args

__all__ = ["Args", "main", "parse_args"]

sys.modules[__name__] = _implementation
