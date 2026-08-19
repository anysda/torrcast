"""Собирает команду ``cast status``: сеанс поверх юнита плюс сценарий состояния.
Зовёт её :func:`torrcast.cli.main.main`.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.adapters.console.print_console import PrintConsole
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.system_clock import SystemClock
from torrcast.domain.config import Config
from torrcast.runtime.playback_session import playback_session
from torrcast.usecases.status import Status


def status_command(settings: Callable[[], Config] = load_config) -> int:
    """``cast status`` — что играет, позиция/длительность, источник.

    Конфиг читается один раз и целиком отдаётся сеансу: и запас в кэше службы, и адрес
    раздачи, и имя приёмника - ответы одного и того же файла, а не трёх его чтений.
    Чтение названо параметром: «один раз» - это счёт вызовов, и считать их вправе тот,
    кто чтение и подставил.
    """
    config = settings()
    return Status(playback_session(lambda: config), PrintConsole(), SystemClock()).run()
