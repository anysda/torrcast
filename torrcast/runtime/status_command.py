"""Собирает команду ``cast status``: сеанс поверх юнита плюс сценарий состояния.
Зовёт её :func:`torrcast.commands.main`.
"""

from __future__ import annotations

from torrcast.adapters.console.print_console import PrintConsole
from torrcast.adapters.system_clock import SystemClock
from torrcast.ports.module import module
from torrcast.runtime.playback_session import playback_session
from torrcast.usecases.status import Status


def status_command() -> int:
    """``cast status`` — что играет, позиция/длительность, источник.

    Конфиг читается один раз и целиком отдаётся сеансу: и запас в кэше службы, и адрес
    раздачи, и имя приёмника - ответы одного и того же файла, а не трёх его чтений.
    """
    config = module("torrcast.commands").load_config()
    return Status(playback_session(lambda: config), PrintConsole(), SystemClock()).run()
