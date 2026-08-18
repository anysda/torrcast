"""Слот внешнего мира меню: правила соседних сценариев и ввод-вывод пульта.

Ставит его совместимый фасад :mod:`torrcast.choice`, спрашивают все единицы пакета."""

from __future__ import annotations

from torrcast.ports.choice_environment import ChoiceEnvironment

_environment: ChoiceEnvironment


def configure(environment: ChoiceEnvironment) -> None:
    """Передать сценарию правила соседних сценариев и ввод-вывод."""
    global _environment
    _environment = environment


def _environment_port() -> ChoiceEnvironment:
    """Внешний мир меню, поставленный :func:`configure`."""
    return _environment
