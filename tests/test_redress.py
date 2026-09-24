"""Дозапрос обложек готового списка: имена прибавляются, сменённый кругом список цел."""

from __future__ import annotations

from typing import Any

import pytest

from hass.redress import _redress, redress
from hass.search_job import SearchJob


def test_a_redress_adds_names_and_leaves_a_list_the_circle_replaced() -> None:
    """Дозапрос прибавляет имена; досчитанный за это время круг он не затирает."""
    job = SearchJob()
    job.settle([{"key": "a", "poster": "pa"}, {"key": "b"}], landed=True)
    assert job._claim_verdict()
    _redress(job, lambda records: [{"key": "a"}, {"key": "b", "poster": "pb"}])
    assert job.results == [{"key": "a", "poster": "pa"}, {"key": "b", "poster": "pb"}]

    def late(records: list[Any]) -> list[Any]:
        job.settle([{"key": "circle"}], landed=True)
        return [{**record, "poster": "late"} for record in records]

    assert job._claim_verdict()
    _redress(job, late)
    assert job.results == [{"key": "circle"}]


def test_a_redress_ends_the_judging_it_was_started_under() -> None:
    """Опрос заводит дозапрос под флагом приговора: без его снятия второй не заводится."""
    job = SearchJob()
    job.settle([{"key": "a"}], landed=True)
    assert job._claim_verdict()
    _redress(job, lambda records: records)
    assert job.judging is False


def test_a_redress_that_fell_still_ends_the_judging_it_was_started_under() -> None:
    """🔴 Упавший дозапрос снимает флаг: иначе заход минуту стоит без единой картинки.

    Пока флаг поднят, опрос считает обложки идущими, второй дозапрос не заводится, а
    заход не сменяется свежим до ``POSTERS_BY``. Ответ короче списка роняет ``zip``.
    """
    job = SearchJob()
    job.settle([{"key": "a"}, {"key": "b"}], landed=True)
    assert job._claim_verdict()

    try:
        _redress(job, lambda records: [])
    except ValueError:
        pass
    else:  # pragma: no cover - страховка теста, а не путь работы
        raise AssertionError("короткий ответ обязан уронить zip: тест ничего не проверил")

    assert job.judging is False, "замок приговора остался у упавшего дозапроса"


def test_a_redress_whose_thread_did_not_start_releases_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Thread.start itself may fail; the next poll must still be able to try again."""

    def fail_start(_thread: object) -> None:
        raise RuntimeError("thread did not start")

    monkeypatch.setattr("hass.redress.threading.Thread.start", fail_start)
    job = SearchJob()

    with pytest.raises(RuntimeError, match="thread did not start"):
        redress(job, lambda records: records)

    assert job.judging is False
