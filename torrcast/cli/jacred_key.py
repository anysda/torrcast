"""Команда ``cast --jacred-key``: сохранить личный ключ JacRed без его печати."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.args import Args

_REMEMBER: Callable[[str], int]


def _configure_jacred_key(remember: Callable[[str], int]) -> None:
    """Назначить сценарий сохранения ключа при сборке CLI."""
    global _REMEMBER
    _REMEMBER = remember


def jacred_key(args: Args, remember: Callable[[str], int] | None = None) -> int:
    """Записать ключ; значение сюда не печатается и не уходит в след."""
    if args.jacred_key is None:
        return 0
    scenario = _REMEMBER if remember is None else remember
    return scenario(args.jacred_key)
