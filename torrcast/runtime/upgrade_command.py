"""Собирает команду ``cast --upgrade``: сеанс показа, консоль и живая система.
Зовёт её :func:`torrcast.cli.main.main`.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.adapters.console.print_console import PrintConsole
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.system_upgrade_environment import SystemUpgradeEnvironment
from torrcast.domain.config import Config
from torrcast.domain.version import __version__
from torrcast.runtime.playback_session import playback_session
from torrcast.usecases.upgrade import Upgrade


def upgrade_command(settings: Callable[[], Config] = load_config) -> int:
    """``cast --upgrade`` - узнать последнюю версию и переставить продукт до неё.

    Язык берётся из той же настройки, что и весь остальной разговор: установщик за
    трубой обязан говорить на языке человека, а не на языке своего умолчания. Конфиг
    читается один раз и отдаётся обоим - и сеансу показа, и выбору языка.
    """
    config = settings()
    return Upgrade(
        playback_session(lambda: config),
        PrintConsole(),
        SystemUpgradeEnvironment(),
        __version__,
        config.language,
    ).run()
