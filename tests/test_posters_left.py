"""Остаток потолка дозапроса обложек: от начала захода, а не от опроса вкладки."""

from __future__ import annotations

import time

import pytest

import hass.search_progress as progress
from hass.posters_left import posters_left
from hass.search_job import POSTERS_BY, SearchJob


def test_a_tab_opened_after_the_job_gets_what_is_left_of_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Вкладка, открытая через 50 с после захода, получает 10 с, а не весь потолок."""
    job = SearchJob()
    job.started_at = time.monotonic() - (POSTERS_BY - 10.0)
    monkeypatch.setattr(progress, "_jobs", {"тачки": job})

    assert 9.0 < posters_left(" Тачки ") <= 10.0, "потолок назван от опроса, а не от захода"
    job.started_at -= 20.0
    assert posters_left("тачки") == 0.0
    assert posters_left("чужой запрос") == 0.0
