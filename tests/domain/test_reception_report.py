"""Зеркало :mod:`torrcast.domain.reception_report`."""

from __future__ import annotations

from torrcast.domain.reception_report import TAIL_SECONDS, ReceptionReport


def test_a_clean_run_is_accepted_and_a_broken_one_is_not() -> None:
    """Приёмка сходится, только если сошлось всё сразу: куски, дыры, CORS и декод."""
    assert ReceptionReport(segments=1800, duration=7200.0, decoded=7199.0).ok
    assert not ReceptionReport(segments=1800, duration=7200.0, decoded=7199.0, gaps=1).ok
    assert not ReceptionReport(segments=1800, duration=7200.0, decoded=7199.0, no_cors=1).ok
    assert not ReceptionReport(segments=1800, duration=7200.0, decoded=3000.0).ok, (
        "оборвался посередине"
    )
    assert not ReceptionReport().ok, "приёмник вообще ничего не увидел"


def test_the_tail_of_one_segment_still_counts_as_the_whole_film() -> None:
    """Декодеру разрешено не дотянуть до конца манифеста ровно на хвост в один сегмент."""
    whole = 7200.0
    assert ReceptionReport(segments=1, duration=whole, decoded=whole - TAIL_SECONDS).ok
    assert not ReceptionReport(segments=1, duration=whole, decoded=whole - TAIL_SECONDS - 0.1).ok


def test_the_line_names_every_number_of_the_run() -> None:
    """Строка приёмки называет все цифры: по ней прогон читают, не открывая отчёт."""
    line = ReceptionReport(
        segments=12, duration=120.0, decoded=119.0, gaps=1, peak_mbit=18.5, no_cors=2
    ).line()

    assert "сегментов 12" in line and "манифест 120 с" in line
    assert "декодировано 119 с" in line and "разрывов 1" in line
    assert "без CORS 2" in line and "пик 18.5 Мбит/с" in line
