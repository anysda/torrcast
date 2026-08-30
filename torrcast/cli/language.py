"""Команда ``cast --ru`` / ``cast --en``: запомнить язык человека в настройке.
Зовёт её :func:`torrcast.cli.main.main` - и как всю работу голого флага, и перед
работой, названной рядом с ним.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.args import Args

#: Кем отвечает флаг языка. Кладёт сюда композиционный корень
#: (:mod:`torrcast.runtime.configure_cli`): слой команд не вправе видеть ни файл
#: настроек, ни консоль, которой сказано о переключении.
_REMEMBER: Callable[[str], int]


def _configure_language(remember: Callable[[str], int]) -> None:
    """Назначить, каким сценарием запоминается выбранный язык."""
    global _REMEMBER
    _REMEMBER = remember


def language(args: Args, remember: Callable[[str], int] | None = None) -> int:
    """Запомнить названный флагом язык; без флага менять нечего."""
    if args.language is None:
        return 0
    scenario = _REMEMBER if remember is None else remember
    return scenario(args.language)
