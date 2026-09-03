"""Сущность медиаплеера: что она показывает и что уходит на серве по кнопкам."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant  # type: ignore[import-not-found]
from homeassistant.exceptions import HomeAssistantError  # type: ignore[import-not-found]
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-not-found]
    MockConfigEntry,
)

from tests.hass_integration.conftest import BASE, DOMAIN, HOST, PORT, mount, sent, snapshot

#: Entity id the recorded fixture's receiver ("192.168.1.90") slugifies to.
PLAYER = "media_player.torrcast_192_168_1_90"


@pytest.fixture(autouse=True)
def _custom_integrations(request: Any) -> None:
    """Даёт Home Assistant увидеть `custom_components/torrcast` в дереве репозитория."""
    request.getfixturevalue("enable_custom_integrations")
    mount()


async def _added(hass: HomeAssistant, aioclient_mock: Any, state: dict[str, Any]) -> Any:
    """Заводит запись на записанном снимке и доводит её до живой сущности."""
    aioclient_mock.get(f"{BASE}/api/state", json=state)
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": HOST, "port": PORT}, unique_id=f"{HOST}:{PORT}"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize(
    ("served", "shown"),
    [
        ("idle", "idle"),
        ("starting", "buffering"),
        ("playing", "playing"),
        ("paused", "paused"),
        ("torn", "idle"),
    ],
)
async def test_states_are_mapped(
    hass: HomeAssistant, aioclient_mock: Any, served: str, shown: str
) -> None:
    """Все пять слов договора переводятся в состояния Home Assistant."""
    await _added(hass, aioclient_mock, snapshot(state=served))
    assert hass.states.get(PLAYER).state == shown


async def test_the_snapshot_becomes_attributes(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Заголовок, серия, позиция, громкость и хозяйство серве видны на карточке."""
    entry = await _added(hass, aioclient_mock, snapshot())
    assert entry.runtime_data.update_interval == timedelta(seconds=5)
    shown = hass.states.get(PLAYER).attributes
    assert shown["media_title"] == "Чернобыль 1 s1e1"
    assert shown["media_season"] == "1"
    assert shown["media_episode"] == "1"
    assert shown["media_position"] == 2
    assert shown["media_duration"] == 3536
    assert shown["volume_level"] == 0.3333333432674408
    assert shown["warm"] == 0
    assert shown["disk_free"] == 67472654336


async def test_entity_is_named_after_torrcast_and_its_receiver(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """§4.1/§4.2: два стенда обязаны звучать по-разному, и оба - словом torrcast."""
    await _added(hass, aioclient_mock, snapshot(tv="192.168.1.90"))
    state = hass.states.get("media_player.torrcast_192_168_1_90")
    assert state is not None, "entity_id без приёмника в имени - сущность не найдена"
    assert state.name == "torrcast 192.168.1.90"


async def test_a_second_receiver_gets_its_own_entity(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Другой приёмник в сети - другая сущность, не переезд той же карточки."""
    await _added(hass, aioclient_mock, snapshot(tv="192.168.1.91"))
    assert hass.states.get("media_player.torrcast_192_168_1_91") is not None
    assert hass.states.get("media_player.torrcast_192_168_1_90") is None


async def test_a_missing_receiver_does_not_spell_out_none(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Приёмник не найден - карточка называется просто torrcast, не torrcast_none."""
    await _added(hass, aioclient_mock, snapshot(tv=None))
    assert hass.states.get("media_player.torrcast") is not None
    assert hass.states.get("media_player.torrcast_none") is None


async def test_empty_fields_do_not_break_the_entity(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Пустым в снимке может быть всё, кроме версии, телевизора и состояния."""
    bare = {"version": "0.99.99", "tv": "TV", "state": "idle"}
    entry = await _added(hass, aioclient_mock, bare)
    assert entry.runtime_data.update_interval == timedelta(seconds=30)
    shown = hass.states.get("media_player.torrcast_tv")
    assert shown is not None, "на снимке из пустых полей сущность не завелась вовсе"
    assert shown.state == "idle"
    assert shown.attributes.get("media_title") is None
    assert shown.attributes.get("volume_level") is None


@pytest.mark.parametrize(
    ("service", "extra", "path", "body"),
    [
        (
            "play_media",
            {"media_content_id": "игра престолов s01e03", "media_content_type": "video"},
            "/api/play",
            {"query": "игра престолов s01e03"},
        ),
        ("media_pause", {}, "/api/control", {"cmd": "toggle"}),
        ("media_play", {}, "/api/control", {"cmd": "toggle"}),
        ("media_stop", {}, "/api/control", {"cmd": "stop"}),
        (
            "media_seek",
            {"seek_position": 1300},
            "/api/control",
            {"cmd": "seekby", "arg": 1297.3},
        ),
        ("volume_set", {"volume_level": 0.7}, "/api/control", {"cmd": "volume", "arg": 0.7}),
        ("volume_up", {}, "/api/control", {"cmd": "volume", "arg": 0.383}),
        ("volume_down", {}, "/api/control", {"cmd": "volume", "arg": 0.283}),
        ("media_next_track", {}, "/api/next", None),
    ],
)
async def test_services_send_the_expected_request(
    hass: HomeAssistant,
    aioclient_mock: Any,
    service: str,
    extra: dict[str, Any],
    path: str,
    body: dict[str, Any] | None,
) -> None:
    """Каждая кнопка карточки уходит своим запросом с ожидаемым телом."""
    await _added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(f"{BASE}{path}", status=204)
    await hass.services.async_call(
        "media_player", service, {"entity_id": PLAYER, **extra}, blocking=True
    )
    posted = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert len(posted) == 1
    assert str(posted[0][1]) == f"{BASE}{path}"
    assert sent(posted[0]) == body


async def test_a_refusal_becomes_a_readable_failure(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """409 от серве доходит до человека словами, а состояние остаётся прежним."""
    await _added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(f"{BASE}/api/next", status=409, json={"error": "no_next"})
    with pytest.raises(HomeAssistantError, match="next episode"):
        await hass.services.async_call(
            "media_player", "media_next_track", {"entity_id": PLAYER}, blocking=True
        )
    assert hass.states.get(PLAYER).state == "playing"


async def test_a_volume_step_without_a_level_is_refused(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Шаг громкости не от чего считать: выдуманный уровень не уходит на приёмник."""
    await _added(hass, aioclient_mock, snapshot(volume=None))
    with pytest.raises(HomeAssistantError, match="volume"):
        await hass.services.async_call(
            "media_player", "volume_up", {"entity_id": PLAYER}, blocking=True
        )
    assert not [call for call in aioclient_mock.mock_calls if call[0] == "POST"]


async def test_search_media_keeps_the_serves_order(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """`async_search_media` asks `/api/search` and hands the answer back untouched in order."""
    await _added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(
        f"{BASE}/api/search",
        json={
            "results": [
                {
                    "pick": 1,
                    "key": "movie:матрица:1999",
                    "title": "Матрица",
                    "year": 1999,
                    "kind": "movie",
                },
                {
                    "pick": 2,
                    "key": "tv:чернобыль:2019",
                    "title": "Чернобыль",
                    "year": 2019,
                    "kind": "tv",
                },
            ]
        },
    )
    answer = await hass.services.async_call(
        "media_player",
        "search_media",
        {"entity_id": PLAYER, "search_query": "матрица"},
        blocking=True,
        return_response=True,
    )
    posted = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert sent(posted[0]) == {"query": "матрица"}
    hits = answer[PLAYER].result
    assert [hit.title for hit in hits] == ["Матрица (1999)", "Чернобыль (2019)"]
    assert hits[0].media_class == "movie"
    assert hits[0].can_play is True
    assert hits[1].media_class == "tv_show"
    assert hits[0].media_content_id == (
        "torrcast://pick/1?q=%D0%BC%D0%B0%D1%82%D1%80%D0%B8%D1%86%D0%B0"
    )


async def test_search_media_relays_the_serves_refusal(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """A 409 from `/api/search` reads like any other refusal, not an invented sentence."""
    await _added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(f"{BASE}/api/search", status=409, json={"error": "busy"})
    with pytest.raises(HomeAssistantError, match="already starting"):
        await hass.services.async_call(
            "media_player",
            "search_media",
            {"entity_id": PLAYER, "search_query": "матрица"},
            blocking=True,
            return_response=True,
        )


async def test_playing_a_picked_search_hit_names_its_pick(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """A `media_content_id` from a search result plays THAT picture, not an auto-pick."""
    await _added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(f"{BASE}/api/play", status=204)
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": PLAYER,
            "media_content_id": "torrcast://pick/2?q=%D0%BC%D0%B0%D1%82%D1%80%D0%B8%D1%86%D0%B0",
            "media_content_type": "video",
        },
        blocking=True,
    )
    posted = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert sent(posted[0]) == {"query": "матрица", "pick": 2}


async def test_browse_media_root_has_one_searchable_child(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """The search field only draws past the root, so the root needs a child to hold it."""
    await _added(hass, aioclient_mock, snapshot())
    root = await hass.services.async_call(
        "media_player",
        "browse_media",
        {"entity_id": PLAYER},
        blocking=True,
        return_response=True,
    )
    child = root[PLAYER].children[0]
    assert child.can_search is True
    assert child.can_expand is True

    inside = await hass.services.async_call(
        "media_player",
        "browse_media",
        {"entity_id": PLAYER, "media_content_id": child.media_content_id},
        blocking=True,
        return_response=True,
    )
    #: Empty before a search, but still a legible folder, not a dead end.
    assert inside[PLAYER].children == []
    assert inside[PLAYER].can_search is True
    assert inside[PLAYER].title


async def test_the_same_failure_is_told_once(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Один и тот же `last_error` показывается один раз, а не на каждом опросе."""
    entry = await _added(hass, aioclient_mock, snapshot(last_error=None))
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/api/state", json=snapshot(last_error="торрент не открылся"))
    told = "custom_components.torrcast.coordinator.persistent_notification.async_create"
    with patch(told) as notice:
        await entry.runtime_data.async_refresh()
        await entry.runtime_data.async_refresh()
    assert notice.call_count == 1
    assert notice.call_args.args[1] == "торрент не открылся"
    assert hass.states.get(PLAYER).attributes["last_error"] == "торрент не открылся"
