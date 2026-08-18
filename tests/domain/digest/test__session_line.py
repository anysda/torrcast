"""Зеркало :mod:`torrcast.domain.digest._session_line`: начало, конец и потери ленты."""

from __future__ import annotations

from tests.domain.digest.rows import rec
from torrcast.domain.digest._session_line import _session_line

STAMP = "+   0.0с "


def test_an_event_of_another_phase_is_not_this_readers_business() -> None:
    """``None`` - «не моё»; пустая строка у конца сеанса - «моё, и печатает его итог»."""
    assert _session_line(rec("buffering"), STAMP) is None
    assert _session_line(rec("session_end", phase="session"), STAMP) == ""


def test_a_start_without_a_profile_says_nothing_about_it() -> None:
    """В ленте прежних версий профиля нет вовсе - и «профиль ?» писать нельзя."""
    told = _session_line(rec("session_start", phase="session", title="Дюна", pos=0.0), STAMP)

    assert told == f"{STAMP}показ «Дюна» с 0:00"


def test_the_thresholds_are_printed_together_with_where_each_of_them_came_from() -> None:
    """Пороги - завоёванные замерами числа, и молчать о том, чьи они, нельзя.

    Без источника строка не отвечает на главный вопрос разбора: играли по профилю
    приёмника или по тому, что человек вписал руками.
    """
    told = _session_line(
        rec(
            "session_start",
            phase="session",
            title="Дюна",
            pos=90.0,
            profile="q70d",
            profile_source="паспорт",
            thresholds={"burst": 60},
            threshold_sources={"burst": "профиль"},
        ),
        STAMP,
    )

    assert told is not None
    assert "показ «Дюна» с 1:30 · профиль q70d (паспорт) · пороги: burst=60 [профиль]" in told


def test_a_profile_without_thresholds_stops_at_the_profile() -> None:
    """Порогов в записи нет - и двоеточия с пустым хвостом тоже быть не должно."""
    told = _session_line(
        rec("session_start", phase="session", title="Дюна", pos=0.0, profile="q70d"), STAMP
    )

    assert told is not None and told.endswith("профиль q70d")


def test_lost_records_are_told_out_loud_because_decisions_went_with_them() -> None:
    """Очередь следа переполнилась - значит решений в ленте НЕТ, и молчать об этом нельзя."""
    told = _session_line(rec("lost", phase="session", count=8), STAMP)

    assert told is not None and "потеряно записей 8" in told
