"""Команда ``cast --tv [ip]``: единственная настройка - адрес телевизора.
Зовёт её :func:`torrcast.cli.main.main`, сценарий ей собирает
:func:`torrcast.runtime.configure_command.configure_command`.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.cli.parse_args import TV_MENU
from torrcast.domain.args import Args

#: Кем отвечает ``cast --tv``. Кладёт сюда композиционный корень
#: (:mod:`torrcast.runtime.wire`): слой команд не вправе видеть адаптеры, которыми
#: сценарий настройки ходит в сеть и в конфиг.
_SETTINGS: Callable[[str | None], int]


def _configure_settings(settings: Callable[[str | None], int]) -> None:
    """Назначить, каким сценарием отвечает ``cast --tv``."""
    global _SETTINGS
    _SETTINGS = settings


def configure(args: Args, command: Callable[[str | None], int] | None = None) -> int:
    """``cast --tv [ip]`` — записать названный адрес или выбрать его из найденных.

    ``--tv`` без адреса - это меню: приёмники ищет сам сценарий настройки, и вместо
    строки-заглушки он получает ``None``.
    """
    scenario = _SETTINGS if command is None else command
    return scenario(None if args.tv == TV_MENU else str(args.tv))
