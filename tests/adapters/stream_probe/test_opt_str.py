"""Непустое значение строкой: пустота и отсутствие отвечают одинаково - ``None``."""

from __future__ import annotations

from torrcast.adapters.stream_probe.opt_str import _opt_str


def test_an_empty_tag_is_the_same_as_no_tag_at_all() -> None:
    """Пустой тег в паспорте - это молчание, а не пустая строка на экране меню озвучек."""
    assert _opt_str(None) is None
    assert _opt_str("") is None


def test_a_value_that_is_there_comes_back_as_a_string() -> None:
    """Ffprobe отдаёт и числа, и строки, а паспорту нужна одна форма."""
    assert _opt_str("rus") == "rus"
    assert _opt_str(0) == "0", "ноль - это значение, а не пустота"
    assert _opt_str(5) == "5"
