"""Дозапрос обложек готового списка: имена прибавляются, сменённый кругом список цел."""

from __future__ import annotations

from typing import Any

from hass.redress import _redress
from hass.search_job import SearchJob


def test_a_redress_adds_names_and_leaves_a_list_the_circle_replaced() -> None:
    """Дозапрос прибавляет имена; досчитанный за это время круг он не затирает."""
    job = SearchJob()
    job.settle([{"key": "a", "poster": "pa"}, {"key": "b"}], landed=True)
    _redress(job, lambda records: [{"key": "a"}, {"key": "b", "poster": "pb"}])
    assert job.results == [{"key": "a", "poster": "pa"}, {"key": "b", "poster": "pb"}]

    def late(records: list[Any]) -> list[Any]:
        job.settle([{"key": "circle"}], landed=True)
        return [{**record, "poster": "late"} for record in records]

    _redress(job, late)
    assert job.results == [{"key": "circle"}]


def test_a_redress_ends_the_judging_it_was_started_under() -> None:
    """Опрос заводит дозапрос под флагом приговора: без его снятия второй не заводится."""
    job = SearchJob()
    job.settle([{"key": "a"}], landed=True)
    job.judging = True
    _redress(job, lambda records: records)
    assert job.judging is False


def test_a_redress_that_fell_still_ends_the_judging_it_was_started_under() -> None:
    """🔴 Упавший дозапрос снимает флаг: иначе заход минуту стоит без единой картинки.

    Пока флаг поднят, опрос считает обложки идущими, второй дозапрос не заводится, а
    заход не сменяется свежим до ``POSTERS_BY``. Ответ короче списка роняет ``zip``.
    """
    job = SearchJob()
    job.settle([{"key": "a"}, {"key": "b"}], landed=True)
    job.judging = True

    try:
        _redress(job, lambda records: [])
    except ValueError:
        pass
    else:  # pragma: no cover - страховка теста, а не путь работы
        raise AssertionError("короткий ответ обязан уронить zip: тест ничего не проверил")

    assert job.judging is False, "флаг приговора остался поднят у упавшего дозапроса"
