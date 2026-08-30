"""Команда ``cast -tg``: передаёт управление меню настройки Telegram."""

from __future__ import annotations

from collections.abc import Callable

from tgbot.wizard import wizard
from torrcast.domain.args import Args


def telegram(args: Args, setup: Callable[[str], int] = wizard) -> int:
    """Запустить меню на выбранном точкой расширения языке."""
    return setup(args.language)
