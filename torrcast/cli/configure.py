"""Команда ``cast --tv [ip]``: единственная настройка - адрес телевизора.
Зовёт её :func:`torrcast.cli.main.main`, сценарий ей собирает
:func:`torrcast.runtime.configure_command.configure_command`.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.cli.args import Args
from torrcast.cli.parse_args import TV_MENU
from torrcast.ports.module import module

#: Композиционный корень зовётся по имени: слой команд не вправе видеть адаптеры,
#: которыми сценарий настройки ходит в сеть и в конфиг.
_SETTINGS: Callable[[str | None], int] = module(
    "torrcast.runtime.configure_command"
).configure_command


def configure(args: Args, command: Callable[[str | None], int] = _SETTINGS) -> int:
    """``cast --tv [ip]`` — записать названный адрес или выбрать его из найденных.

    ``--tv`` без адреса - это меню: приёмники ищет сам сценарий настройки, и вместо
    строки-заглушки он получает ``None``.
    """
    return command(None if args.tv == TV_MENU else str(args.tv))
