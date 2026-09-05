"""Площадка медиаплеера: одна запись поднимает ровно одну сущность и снимает её же."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from tests.hass_integration.conftest import PLAYER
from tests.hass_integration.helpers import added


async def test_one_entry_raises_exactly_one_entity(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Один серв - один телевизор: площадка заводит одну сущность, а не список.

    Имя файла тут - имя ПЛОЩАДКИ Home Assistant, а не единицы внутри, поэтому правило
    «имя» с него снято поимённо (`scripts/structure_gate.py`, `HOME_ASSISTANT_SHAPE`).
    Всё, что показывает и умеет сама сущность, спрашивается с её собственных зеркал:
    `test_player.py`, `test_remote.py`, `test_browsing.py`.
    """
    idle = {"version": "0.99.99", "tv": "192.168.1.90", "state": "idle"}
    await added(hass, aioclient_mock, idle)
    players = list(hass.states.async_entity_ids("media_player"))

    assert players == [PLAYER]


async def test_unloading_the_entry_takes_the_entity_down(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Запись сняли - карточка говорит «недоступна», а не держит последний снимок.

    Сущность остаётся в реестре Home Assistant (иначе человек потерял бы её из
    панелей), но показывать ей больше нечего, и снимок серва она за собой не тащит.
    """
    entry = await added(hass, aioclient_mock, {"version": "0.99.99", "tv": "TV", "state": "idle"})

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("media_player.torrcast_tv").state == "unavailable"
