"""Диалог обзора и поисковая строка со стороны сущности: что она делает с вводом."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_component import DATA_INSTANCES

from hass.hit_posters import FIELD
from tests.hass_integration.conftest import BASE, PLAYER, sent, snapshot
from tests.hass_integration.helpers import added, served
from torrcast.domain.picture import Picture


async def test_a_hit_shows_its_poster_and_home_assistant_fetches_it_from_the_serve(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """A found picture is drawn with its poster, and the bytes come from the serve.

    The serve names the poster of a hit and nothing else: the name is not an address, so
    the browser has nowhere to go with it. The thumbnail points at Home Assistant's own
    browse-image proxy, which lands back on the entity here in the house and asks the
    serve's `/api/poster/` route for the bytes - the same pair of hops the card's own
    picture already crosses, and neither of them leaves for the outside.

    A hit the serve found no picture for keeps no thumbnail at all: a row stays a row,
    with no placeholder and no empty frame around nothing.
    """
    await added(hass, aioclient_mock, snapshot())
    answer = served(
        [Picture(title="Матрица", year=1999), Picture(title="Чернобыль", year=2019, kind="tv")],
        taken=1,
    )
    body = b"\x89PNG\r\n\x1a\n poster"
    answer["results"][0][FIELD] = "8b1d3f0c11d2a4e6"
    aioclient_mock.post(f"{BASE}/api/search", json=answer)
    answer = await hass.services.async_call(
        "media_player",
        "search_media",
        {"entity_id": PLAYER, "search_query": "матрица", "media_content_id": "menu"},
        blocking=True,
        return_response=True,
    )
    hits = answer[PLAYER].result

    #: Пустая строка вместо `None` намеренно: снятая правка обязана краснеть утверждением
    #: о том, что человек видит, а не `AttributeError` на отсутствующем адресе.
    shown = hits[0].thumbnail or ""
    assert shown.startswith(f"/api/media_player_proxy/{PLAYER}/browse_media/")
    assert "media_image_id=8b1d3f0c11d2a4e6" in shown
    assert hits[1].thumbnail is None

    aioclient_mock.get(
        f"{BASE}/api/poster/8b1d3f0c11d2a4e6", content=body, headers={"Content-Type": "image/png"}
    )
    entity = hass.data[DATA_INSTANCES]["media_player"].get_entity(PLAYER)
    shot, kind = await entity.async_get_browse_image(
        hits[0].media_content_type, hits[0].media_content_id, "8b1d3f0c11d2a4e6"
    )

    assert (shot, kind) == (body, "image/png")
    assert f"{BASE}/api/poster/8b1d3f0c11d2a4e6" in [
        str(call[1]) for call in aioclient_mock.mock_calls
    ]


async def test_search_media_relays_the_serves_refusal(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """A 409 from `/api/search` reads like any other refusal, not an invented sentence."""
    await added(hass, aioclient_mock, snapshot())
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
    await added(hass, aioclient_mock, snapshot())
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


async def test_the_instant_field_plays_the_typed_name_without_searching(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Typed into instant and sent: the show starts, and no list is asked for.

    This is the whole of the card: the browse dialog hands the node's own id back with
    the typed words appended as `message` and `announce` of its own accord (see
    `browse.py`), and that has to reach the serve as the plain query a bare `cast` would
    take - one step, no pick number invented on the way, no `/api/search` at all.
    """
    await added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(f"{BASE}/api/play", status=202, json={"key": "k"})
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": PLAYER,
            "media_content_id": "media-source://tts/instant?message=%D0%BC%D0%B0%D1%82%D1%80%D0%B8%D1%86%D0%B0",
            "media_content_type": "audio/mp3",
            "announce": True,
        },
        blocking=True,
    )
    posted = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert [str(call[1]) for call in posted] == [f"{BASE}/api/play"], (
        "инстант обязан включать показ сам, а не спрашивать список"
    )
    assert sent(posted[0]) == {"query": "матрица"}
