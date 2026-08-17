"""Проверяет перевод минут в человеческую строку хронометража."""

from torrcast.domain.facts.hms import hms


def test_running_time_reads_as_a_human_would_say_it() -> None:
    assert hms(116) == "1 ч 56 мин"
    assert hms(47) == "47 мин"
    assert hms(60) == "1 ч", "«1 ч 0 мин» так не говорят"
    assert hms(0) == ""
