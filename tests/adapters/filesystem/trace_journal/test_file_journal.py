"""Лента за портом журнала: тот же файл и та же схема, только объектом."""

from __future__ import annotations

from torrcast.adapters.filesystem.stopwatch import mark
from torrcast.adapters.filesystem.trace_journal import dark, emit, nudge, records, segment
from torrcast.adapters.filesystem.trace_journal.file_journal import FileJournal
from torrcast.ports.journal import Journal


def test_the_object_calls_the_very_same_functions_and_not_a_second_copy_of_the_schema() -> None:
    """За портом стоят те же функции: вторая раскладка полей разошлась бы с ``cast log``.

    Заведи объект свои ``emit`` и свои имена полей - и половина показа писала бы одну
    схему, половина другую, а разбор недели не увидел бы ни одной целиком.
    """
    journal = FileJournal()

    assert journal.emit is emit
    assert journal.mark is mark
    assert journal.records is records
    assert journal.nudge is nudge
    assert journal.segment is segment
    assert journal.dark is dark


def test_the_object_answers_the_whole_contract_the_layers_are_given() -> None:
    """Слои знают только договор порта - объект обязан отвечать на него целиком."""
    journal: Journal = FileJournal()

    for name in (
        "emit",
        "mark",
        "shutdown",
        "records",
        "session_id",
        "start_session",
        "health",
        "nudge",
        "segment",
        "plan",
        "reload",
        "offline",
        "resupply",
        "dark",
        "revive",
        "seek",
        "evict",
        "skew",
        "warmth",
    ):
        assert callable(getattr(journal, name)), f"порт спрашивает {name}, а его нет"
