"""Секунды в «ч:мм:сс»: минуты и секунды всегда двузначные."""

from __future__ import annotations

from torrcast.usecases.rank._hms import _hms


def test_seconds_are_printed_as_hours_minutes_seconds() -> None:
    assert _hms(0) == "0:00:00"
    assert _hms(3725) == "1:02:05"
    assert _hms(86399) == "23:59:59"


def test_a_fraction_is_dropped_not_rounded_up() -> None:
    """Иначе показ на 59.9 с называется минутой, которой ещё не было."""
    assert _hms(59.9) == "0:00:59"
