"""Командная строка torrcast и совместимый фасад её предметных частей.

Точка входа намеренно остаётся здесь. Имена прежнего монолита также доступны
отсюда: ими пользуются тесты и внешние диагностические сценарии.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from torrcast import choice as _choice_module
from torrcast import commands as _commands_module
from torrcast import discovery as _discovery_module
from torrcast import play_command as _play_command_module
from torrcast import playback as _playback_module
from torrcast import ranking as _ranking_module
from torrcast import reinforce as _reinforce_module
from torrcast import selection as _selection_module
from torrcast.commands import main
from torrcast.ranking import _hms as _hms

_PARTS = (
    _commands_module,
    _play_command_module,
    _discovery_module,
    _reinforce_module,
    _selection_module,
    _playback_module,
    _choice_module,
    _ranking_module,
)

# Функции в перенесённых частях разрешают глобальные имена в своём модуле.
# Доводим до каждой части полный namespace после завершения цепочки импортов.
_namespace: dict[str, Any] = {}
for _part in _PARTS:
    _namespace.update(
        (name, value)
        for name, value in vars(_part).items()
        if not name.startswith("__")
    )
globals().update(_namespace)
for _part in _PARTS:
    vars(_part).update(_namespace)


class _CliModule(ModuleType):
    """Передаёт тестовые/диагностические подмены в модули реализации."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if not name.startswith("__"):
            for part in _PARTS:
                if name in vars(part):
                    setattr(part, name, value)


sys.modules[__name__].__class__ = _CliModule

__all__ = [name for name in globals() if not name.startswith("_")]


if __name__ == "__main__":
    raise SystemExit(main())
