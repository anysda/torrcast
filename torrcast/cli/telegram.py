"""Команда ``cast -tg``: передаёт управление меню настройки Telegram."""

from __future__ import annotations

from collections.abc import Callable

from tgbot.wizard import wizard
from torrcast.domain.args import Args


def telegram(_args: Args, setup: Callable[[], int] = wizard) -> int:
    """Запустить меню; язык ему называет единый держатель, а флаг языка до этой
    команды уже лёг в настройку (:func:`torrcast.cli.main.main`)."""
    return setup()
