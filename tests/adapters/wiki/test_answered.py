"""Частичный отказ порций - не то же самое, что отказ сети."""

from __future__ import annotations

from concurrent.futures import Future

import pytest

from torrcast.adapters.wiki.answered import answered
from torrcast.domain.json_value import JsonValue


def _done(value: JsonValue) -> Future[JsonValue]:
    task: Future[JsonValue] = Future()
    task.set_result(value)
    return task


def _failed(bad: BaseException) -> Future[JsonValue]:
    task: Future[JsonValue] = Future()
    task.set_exception(bad)
    return task


def test_the_order_of_the_parts_is_the_order_of_the_answers() -> None:
    assert answered([_done({"a": 1}), _done({"b": 2})]) == [{"a": 1}, {"b": 2}]


def test_a_part_that_failed_leaves_the_rest_of_the_answers_in_work() -> None:
    """Одна порция из двух отказала - вторая всё равно приносит свои статьи."""
    assert answered([_failed(OSError("429")), _done({"b": 2})]) == [{"b": 2}]


def test_when_every_part_failed_it_is_the_network_that_refused() -> None:
    """Пусто ото всех - это отказ, а не «статей не нашлось»: иначе промах лёг бы в склад."""
    with pytest.raises(OSError, match="429"):
        answered([_failed(OSError("429")), _failed(OSError("503"))])
