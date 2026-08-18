"""Зеркало :mod:`torrcast.domain.digest._session_block`: один сеанс со своим итогом.

Итог считается по СВОЕЙ ленте: сложись счётчики двух сеансов, вчерашний фильм с двумя
ребуферами и сегодняшний чистый показ читались бы как один плохой вечер.
"""

from __future__ import annotations

from tests.domain.digest.rows import rec
from torrcast.domain.digest._session_block import _session_block
from torrcast.domain.trace_sources import PACKED, WARMED


def test_the_head_names_the_session_and_the_query_it_started_with() -> None:
    """Шапка - это то, по чему человек находит нужный показ в неделе."""
    block = _session_block("abc", [rec("query", phase="search", query="дюна", raw=41, pictures=3)])

    assert block.splitlines()[0].startswith("сеанс abc · ")
    assert "«дюна»" in block.splitlines()[0]


def test_zero_rebuffers_are_said_out_loud() -> None:
    """Ноль ребуферов - тоже новость: молчание не отличалось бы от «ленты нет»."""
    block = _session_block("s", [rec("session_end", phase="session", pos=0.0, dur=0.0)])

    assert "итог: ребуферов 0" in block


def test_what_never_happened_is_not_listed_in_the_summary() -> None:
    """Перечисли итог все нули - строка стала бы нечитаемой ради ничего."""
    block = _session_block("s", [rec("buffering", pos=1.0), rec("nudge", pos=1.0, to=2.0)])

    assert "нуджей сторожа 1" in block
    assert "перемоток" not in block and "обрывов сети" not in block


def test_a_repeated_timeline_phase_is_printed_once_with_a_count() -> None:
    """Упаковка заходит на каждый прыжок: печатай выжимка все - фаза съела бы её целиком."""
    rows = [rec("упаковка", phase="timeline", слот=n) for n in range(3)]

    block = _session_block("s", rows)

    assert block.count("фаза «упаковка»") == 1
    assert "всего 3" in block


def test_the_seams_of_the_session_are_counted_in_its_own_summary() -> None:
    """Стык источника - строка итога, и считается он по записям этого сеанса."""
    rows = [
        rec("segment", slot=1, src=WARMED),
        rec("segment", slot=2, src=PACKED),
        rec("segment", slot=3, src=WARMED),
    ]

    block = _session_block("s", rows)

    assert "стыков источника 2" in block


def test_the_end_tells_a_finished_film_apart_from_an_abandoned_one() -> None:
    """Досмотрено или брошено на такой-то секунде - разные вещи, и путать их нельзя."""
    done = _session_block(
        "s", [rec("session_end", phase="session", pos=7000.0, dur=7200.0, watched=True)]
    )
    left = _session_block("s", [rec("session_end", phase="session", pos=600.0, dur=7200.0)])

    assert "досмотрено" in done and "из 2:00:00" not in done
    assert "остановлено на 10:00 из 2:00:00" in left
