"""Зеркало :mod:`torrcast.domain.trace_sources`: откуда взялся отданный приёмнику кусок.

Поле идёт в КАЖДОЙ записи сегмента, поэтому сторожится не написание строк, а то, ради чего
они есть: два источника обязаны различаться, и разбор ленты обязан знать оба - иначе стык
живой упаковки и прогретого в выжимке не виден вовсе.
"""

from __future__ import annotations

from torrcast.domain.digest import _seams, digest
from torrcast.domain.json_value import JsonValue
from torrcast.domain.trace_sources import PACKED, WARMED


def _segment(sid: str, at: float, src: str) -> dict[str, JsonValue]:
    """Запись отданного куска - ровно то, что пишет лента про один сегмент."""
    return {"at": at, "sid": sid, "phase": "show", "event": "segment", "slot": int(at), "src": src}


def test_the_two_sources_are_told_apart_and_neither_is_silent() -> None:
    """Живая упаковка и прогретое - разные вещи, и записаны они разными строками.

    Сравняй их - и лента перестала бы отвечать на вопрос, ради которого поле заведено:
    кусок приехал из свежей нарезки или его отдали с диска.
    """
    assert len({PACKED, WARMED}) == 2
    assert PACKED and WARMED


def test_a_switch_between_the_two_sources_is_visible_as_a_seam_in_the_trace() -> None:
    """Смена источника посреди показа - это стык, и разбор ленты обязан его найти.

    Первый кусок сеанса стыком не считается: у него нет предыдущего источника. А вот
    переход с прогретого на живую упаковку - именно он, и именно по нему разбирают, где
    показ перестал играть с диска.
    """
    rows = [
        _segment("s1", 1.0, WARMED),
        _segment("s1", 2.0, WARMED),
        _segment("s1", 3.0, PACKED),
    ]
    seams = _seams(rows)
    assert [rec["slot"] for rec in seams] == [3]

    assert _seams(rows[:2]) == [], "показ без смены источника стыков не даёт"


def test_each_source_is_named_in_human_words_in_the_summary() -> None:
    """В выжимке источник зовётся по-русски, а не кодом поля.

    ``cast log`` читает человек, и «pack» ему ничего не говорит. Заведись источник без
    имени в разборе - он попал бы в выжимку сырой строкой поля, и стык читался бы как
    «источник сменился на pack».
    """
    onto_packed = digest([_segment("s1", 1.0, WARMED), _segment("s1", 2.0, PACKED)])
    assert "живая упаковка" in onto_packed
    assert PACKED not in onto_packed

    onto_warmed = digest([_segment("s2", 1.0, PACKED), _segment("s2", 2.0, WARMED)])
    assert "прогретое" in onto_warmed
    assert WARMED not in onto_warmed
