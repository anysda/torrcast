"""Переходный порт доступа к зависимостям совместимых сценариев."""

from types import ModuleType


def module(name: str) -> ModuleType:
    """Вернуть зависимость, которую композиционный фасад называет строкой."""
    return __import__(name, fromlist=("*",))
