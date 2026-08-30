"""Команда ``cast -tg``: передаёт управление меню настройки Telegram."""

from __future__ import annotations

from collections.abc import Callable

from tgbot.wizard import wizard
from torrcast.domain.args import Args


def telegram(args: Args, setup: Callable[[str | None], int] = wizard) -> int:
    """Запустить меню на языке, названном флагом; без флага его берёт сам мастер."""
    return setup(args.language)
