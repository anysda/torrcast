"""Зеркало :mod:`torrcast.domain.uptime_words`."""

from torrcast.domain.uptime_words import uptime_words


def test_less_than_an_hour_is_counted_in_minutes() -> None:
    assert uptime_words(0) == "0 мин"
    assert uptime_words(59) == "0 мин"
    assert uptime_words(3599) == "59 мин"


def test_hours_name_the_minutes_next_to_them() -> None:
    assert uptime_words(3600) == "1 ч 0 мин"
    assert uptime_words(3600 * 5 + 60 * 7) == "5 ч 7 мин"


def test_days_cut_the_minutes_off_as_meaningless() -> None:
    """Минуты рядом с сутками не меняют ни одного вывода, и в строке им места нет."""
    assert uptime_words(86400) == "1 д 0 ч"
    assert uptime_words(86400 * 3 + 3600 * 4 + 59) == "3 д 4 ч"


def test_a_negative_reading_is_not_printed_as_a_negative_span() -> None:
    """Часы прибора могут соврать назад - строка от этого ломаться не должна."""
    assert uptime_words(-5) == "0 мин"
