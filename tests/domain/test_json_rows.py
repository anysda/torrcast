"""Зеркало :mod:`torrcast.domain.json_rows`: массив JSON читается списком, чужое - пустым."""

from __future__ import annotations

from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue


def test_an_array_is_returned_as_it_is() -> None:
    """Список возвращается тем же: по нему тут же идут разбором, а не копией."""
    rows: JsonValue = [{"title": "Дюна"}]

    assert json_rows(rows) is rows


def test_everything_that_is_not_an_array_reads_as_an_empty_list() -> None:
    """Поля нет, поле не массив - перебирать нечего, и это не авария разбора."""
    assert json_rows(None) == []
    assert json_rows({"title": "Дюна"}) == []
    assert json_rows("строка") == []
