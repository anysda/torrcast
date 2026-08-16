"""Загружает совместимые зависимости старого фасада без связи слоя с реализацией."""

from importlib import import_module


def legacy_namespace(**sources: tuple[str, ...]) -> dict[str, object]:
    """Собирает именованные зависимости из модулей, указанных композицией приложения."""
    result: dict[str, object] = {}
    for module_name, names in sources.items():
        module = import_module(module_name.replace("__", "."))
        result.update((name, getattr(module, name)) for name in names)
    return result
