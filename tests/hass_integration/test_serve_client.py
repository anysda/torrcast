"""Клиент серве: сроки запросов и чтение отказов."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import aiohttp
from homeassistant.core import HomeAssistant

from tests.hass_integration.conftest import BASE, snapshot
from tests.hass_integration.helpers import added


async def test_search_waits_longer_than_a_state_poll(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """A search's own timeout has to outlast the plain state poll's, not just exist.

    TC-1002, live acceptance 03-09-2026: a cold search on the stand answered in 11.0 s
    while the state poll's own timeout (10 s) had already run out, and the shared
    constant was blamed. The two requests are timed here as they actually leave the
    coordinator, and compared against EACH OTHER - a constant that merely equals its own
    name would pass a check against itself and hide a regression that made both requests
    share one timeout again.
    """
    entry = await added(hass, aioclient_mock, snapshot())
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/api/state", json=snapshot())
    aioclient_mock.post(f"{BASE}/api/search", json={"results": []})

    coordinator = entry.runtime_data
    real_timeout = aiohttp.ClientTimeout
    seen: list[float] = []

    def _measured(**kwargs: Any) -> aiohttp.ClientTimeout:
        seen.append(kwargs["total"])
        return real_timeout(**kwargs)

    with patch("aiohttp.ClientTimeout", side_effect=_measured):
        await coordinator.async_refresh()
        await coordinator.async_search("матрица")

    assert len(seen) == 2, "ожидались ровно два похода: опрос состояния и поиск"
    state_timeout, search_timeout = seen
    assert search_timeout > state_timeout, "поиск обязан ждать индексаторы дольше опроса"
