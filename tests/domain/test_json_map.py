"""Зеркало :mod:`torrcast.domain.json_map`: объект JSON читается объектом, чужое - пустотой."""

from __future__ import annotations

from torrcast.domain.json_map import json_map
from torrcast.domain.json_value import JsonValue


def test_an_object_is_returned_as_it_is() -> None:
    """Объект возвращается тем же, а не копией: разбор ходит по нему дальше вглубь."""
    inner: JsonValue = {"query": {"pages": []}}

    assert json_map(inner) is inner


def test_everything_that_is_not_an_object_reads_as_an_empty_one() -> None:
    """Нет поля, поле не объект - читателю в обоих случаях перебирать нечего.

    Ровно так разбор и вёл себя всегда: ``rec.get("got") or {}``. Верни правило ошибку -
    ответ справки без одного поля ронял бы весь разбор.
    """
    assert json_map(None) == {}
    assert json_map([1, 2]) == {}
    assert json_map("строка") == {}
    assert json_map(7) == {}
