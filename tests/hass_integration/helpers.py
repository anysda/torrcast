"""Заготовки, общие для набора интеграции: живая запись, ответ серве, чтение ползунка.

Файл лежит рядом с тестами, а не в `conftest.py`, намеренно: `conftest.py` читает и
основной прогон (в нём объявлен отвод каталога), а здесь импорты Home Assistant стоят
наверху, как в самих тестах. Собирать этот файл pytest не станет - имя не тестовое, да и
весь каталог без переменной запускателя отводится целиком.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from hass.search_results import search_results
from tests.hass_integration.conftest import BASE, DOMAIN, HOST, PLAYER, PORT, snapshot
from torrcast.domain.picture import Picture
from torrcast.usecases.select.plan import Plan


async def added(hass: HomeAssistant, aioclient_mock: Any, state: dict[str, Any]) -> Any:
    """Заводит запись на записанном снимке и доводит её до живой сущности."""
    aioclient_mock.get(f"{BASE}/api/state", json=state)
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": HOST, "port": PORT}, unique_id=f"{HOST}:{PORT}"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def served(pictures: list[Picture], taken: int) -> dict[str, Any]:
    """The body of `POST /api/search`, built by the serve's OWN shaping function.

    This is the one guard of the seam between the two halves. Both sides used to be
    nailed to a hand-written literal of their own, so a field renamed on the bridge side
    reddened nothing at all and the break showed up on a live stand. Here the fake serve
    answers with what `hass/search_results.py` actually writes: rename `pick` or
    `default` there and the tests fail, not the television.

    The shaping function costs nothing to import in this venv - it reaches for the
    torrcast domain and for the one usecase that names a picture to a person, and for
    nothing else: no config file, no network, no Home Assistant.
    """
    plans = [Plan(picture=picture, ranked=[], runtime=0.0, warn_mbit=0.0) for picture in pictures]
    return {"results": search_results(plans, taken)}


def drawn(hass: HomeAssistant, moment: datetime) -> float:
    """Где ползунок карточки окажется к этому мигу: место плюс время от метки.

    Считается ровно так, как это делает фронт Home Assistant, - иначе мерялась бы не та
    линия, которую видит человек.
    """
    shown = hass.states.get(PLAYER)
    assert shown is not None
    place = float(shown.attributes["media_position"])
    mark: datetime = shown.attributes["media_position_updated_at"]
    return place + (moment - mark).total_seconds()


async def polled_again(
    hass: HomeAssistant, aioclient_mock: Any, entry: Any, **changes: Any
) -> None:
    """Ещё один круг опроса с другим ответом серва."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/api/state", json=snapshot(**changes))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
