"""Слот консольного порта правил ранжирования.

Ставит его композиционный корень (:func:`torrcast.runtime.wire.wire`), спрашивают
вопрос про озвучку и меню дорожек."""

from __future__ import annotations

from torrcast.ports.console import Console

_console: Console


def configure(console: Console) -> None:
    """Передать сценарию пользовательский ввод и вывод."""
    global _console
    _console = console


def _console_port() -> Console:
    """Консольный порт, поставленный :func:`configure`."""
    return _console
