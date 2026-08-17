"""Штатный выход: дожать хвост ленты, пока писателя ещё не убил конец процесса.

Зовёт его корень запуска и порт журнала, из горячего пути - никогда."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.writer import _writer


def shutdown() -> None:
    """Дожать хвост ленты на штатном выходе. Без вызова хвост теряется - и это допустимо."""
    _writer.stop()
