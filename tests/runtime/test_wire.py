"""Композиционный корень: после сборки след пишет настоящая лента, а не молчание."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal import FileJournal
from torrcast.ports.journal import _Silent, install, journal
from torrcast.runtime.wire import wire


def test_wiring_puts_the_real_journal_on_the_port() -> None:
    """До сборки след молчит, после - пишет; это и есть работа корня."""
    install(_Silent())
    assert isinstance(journal(), _Silent)

    wire()

    assert isinstance(journal(), FileJournal)
