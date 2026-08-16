"""Собирает команду ``cast stop``: сеанс поверх юнита плюс сценарий остановки.
Зовёт её :func:`torrcast.commands.main`.
"""

from __future__ import annotations

from torrcast.adapters.console.print_console import PrintConsole
from torrcast.runtime.playback_session import playback_session
from torrcast.usecases.stop import Stop


def stop_command() -> int:
    """``cast stop`` — снять каст и зафиксировать позицию."""
    return Stop(playback_session(), PrintConsole()).run()
