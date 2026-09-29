"""Каталог сериала из готовых частей: часы говорят тем же видом, что даты TVmaze."""

from datetime import datetime

from torrcast.ports.aired_state import AiredState
from torrcast.runtime.series_facts import SeriesFacts


def test_the_default_clock_is_an_aware_iso_moment() -> None:
    """Даты TVmaze сравниваются строками ISO с поясом: часы обязаны говорить тем же видом."""
    facts = SeriesFacts(lambda *_a: "", lambda _t: None, lambda *_a: ({}, AiredState.KNOWN))
    assert datetime.fromisoformat(facts.now()).utcoffset() is not None
