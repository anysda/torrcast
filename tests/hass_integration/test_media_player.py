"""Сущность медиаплеера: что она показывает и что уходит на серве по кнопкам."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

import aiohttp  # type: ignore[import-not-found]
import pytest
from homeassistant.components.media_player import (  # type: ignore[import-not-found]
    MediaPlayerEntityFeature,
)
from homeassistant.core import HomeAssistant  # type: ignore[import-not-found]
from homeassistant.exceptions import HomeAssistantError  # type: ignore[import-not-found]
from homeassistant.helpers.entity_component import (  # type: ignore[import-not-found]
    DATA_INSTANCES,
)
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-not-found]
    MockConfigEntry,
)

from hass.search_results import search_results
from tests.hass_integration.conftest import BASE, DOMAIN, HOST, PORT, mount, sent, snapshot
from torrcast.domain.kind import Kind
from torrcast.domain.picture import Picture
from torrcast.usecases.select.plan import Plan

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
        ("torn", "buffering"),
    ],
)
async def test_states_are_mapped(
    hass: HomeAssistant, aioclient_mock: Any, served: str, shown: str
) -> None:
    """Все пять слов договора переводятся в состояния Home Assistant.

    `torn` уходит на `buffering`, не `idle`: продукт всё ещё держит показ и обещает
    поднять его сам, а `idle` человек читает как «ничего не идёт».
    """
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
        #: Кнопка питания гасит ПОКАЗ той же командой: телевизор из розетки продукт
        #: не выключает, и новой дороги наружу под кнопку не заводилось.
        ("turn_off", {}, "/api/control", {"cmd": "stop"}),
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
        #: "сначала", not a track before this one: the fixture's own position (2.7 s) is
        #: what the offset is computed from, the same seekby route media_seek already uses.
        ("media_previous_track", {}, "/api/control", {"cmd": "seekby", "arg": -2.7}),
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


async def test_the_card_draws_a_power_button_next_to_the_buttons_it_already_had(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """🔴 Кнопку питания фронт рисует по флагу, и по нему же её не рисует вовсе.

    Человек видел карточку без выключения не потому, что выключать было нечем: `stop`
    жил всё это время. Не заявлен был флаг, а незаявленный флаг фронт читает как
    «плеер так не умеет» и кнопку не рисует. Утверждение тут - про флаги, потому что
    именно они и есть то, что человек видит.

    Соседние флаги названы поимённо: одиннадцать кнопок уже живут на карточке, и
    перебранное выражение с потерянным `|` погасило бы их все, не сказав ни слова.
    """
    await _added(hass, aioclient_mock, snapshot())
    features = MediaPlayerEntityFeature(hass.states.get(PLAYER).attributes["supported_features"])

    assert MediaPlayerEntityFeature.TURN_OFF in features
    #: Включать нечего: показ поднимают запросом, а не питанием. Кнопка, которая ничего
    #: не делает, хуже её отсутствия, поэтому `TURN_ON` не заявлен намеренно.
    assert MediaPlayerEntityFeature.TURN_ON not in features
    for lived_here_before in (
        MediaPlayerEntityFeature.PLAY,
        MediaPlayerEntityFeature.PAUSE,
        MediaPlayerEntityFeature.PLAY_MEDIA,
        MediaPlayerEntityFeature.STOP,
        MediaPlayerEntityFeature.NEXT_TRACK,
        MediaPlayerEntityFeature.PREVIOUS_TRACK,
        MediaPlayerEntityFeature.SEEK,
        MediaPlayerEntityFeature.VOLUME_SET,
        MediaPlayerEntityFeature.VOLUME_STEP,
        MediaPlayerEntityFeature.BROWSE_MEDIA,
        MediaPlayerEntityFeature.SEARCH_MEDIA,
    ):
        assert lived_here_before in features, f"кнопка {lived_here_before.name} пропала с карточки"


async def test_turning_off_an_empty_screen_says_nothing_to_the_person(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Гасить нечего - кнопка молчит, а не роняет отказ серве в лицо.

    Серве на пустом показе отвечает `nothing_playing`, и это правда, но человеку,
    который только что нажал «выключить», она читается как поломка: экран уже там,
    куда он просил. Ни запроса, ни ошибки.
    """
    await _added(hass, aioclient_mock, snapshot(state="idle"))
    #: Подделка отвечает ровно то, что ответил бы серве: `stop` на пустом показе - 409.
    aioclient_mock.post(f"{BASE}/api/control", status=409, json={"error": "nothing_playing"})
    told: list[str] = []

    try:
        await hass.services.async_call(
            "media_player", "turn_off", {"entity_id": PLAYER}, blocking=True
        )
    except HomeAssistantError as refusal:
        told.append(str(refusal))

    assert told == [], f"человеку показали отказ на нажатие «выключить»: {told}"
    assert not [call for call in aioclient_mock.mock_calls if call[0] == "POST"]


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


async def test_a_restart_without_a_known_position_is_refused(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """«Сначала» не от чего отмотать без известной позиции: отказ словами, не исключение."""
    await _added(hass, aioclient_mock, snapshot(position=None))
    with pytest.raises(HomeAssistantError, match="current position"):
        await hass.services.async_call(
            "media_player", "media_previous_track", {"entity_id": PLAYER}, blocking=True
        )
    assert not [call for call in aioclient_mock.mock_calls if call[0] == "POST"]


def _served(pictures: list[tuple[str, int, Kind]], taken: int) -> dict[str, Any]:
    """The body of `POST /api/search`, built by the serve's OWN shaping function.

    This is the one guard of the seam between the two halves. Both sides used to be
    nailed to a hand-written literal of their own, so a field renamed on the bridge side
    reddened nothing at all and the break showed up on a live stand. Here the fake serve
    answers with what `hass/search_results.py` actually writes: rename `pick` or
    `default` there and this test fails, not the television.

    The shaping function costs nothing to import in this venv - it reaches for the
    torrcast domain and for nothing else.
    """
    plans = [
        Plan(
            picture=Picture(title=title, year=year, kind=kind),
            ranked=[],
            runtime=0.0,
            warn_mbit=0.0,
        )
        for title, year, kind in pictures
    ]
    return {"results": search_results(plans, taken)}


async def test_search_media_puts_the_picture_a_bare_play_takes_first(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """One query, one film: `result[0]` is what a bare `POST /api/play` would start.

    Home Assistant's own `MediaSearchAndPlayHandler` plays `result[0]`, so the hit the
    serve flagged `default` has to lead even when the serve lists it second. Everything
    else keeps the serve's order, and every hit keeps its own pick number.

    Searched from the `menu` node - the only field that hands a person a list at all.
    """
    await _added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(
        f"{BASE}/api/search",
        json=_served([("Матрица", 1999, "movie"), ("Чернобыль", 2019, "tv")], taken=2),
    )
    answer = await hass.services.async_call(
        "media_player",
        "search_media",
        {"entity_id": PLAYER, "search_query": "матрица", "media_content_id": "menu"},
        blocking=True,
        return_response=True,
    )
    posted = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert sent(posted[0]) == {"query": "матрица"}
    hits = answer[PLAYER].result
    assert [hit.title for hit in hits] == ["Чернобыль (2019)", "Матрица (1999)"]
    assert hits[0].media_class == "tv_show"
    assert hits[0].can_play is True
    assert hits[1].media_class == "movie"
    #: The number travels inside the id, so moving a hit up the screen does not renumber it.
    assert hits[0].media_content_id == (
        "torrcast://pick/2?q=%D0%BC%D0%B0%D1%82%D1%80%D0%B8%D1%86%D0%B0"
    )
    assert hits[1].media_content_id == (
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
    entry = await _added(hass, aioclient_mock, snapshot())
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


async def test_browse_media_root_puts_menu_first_and_instant_second(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Menu leads, and only menu searches: instant is a field to command from.

    The search field only draws past the root, so each mode needs a child of its own.
    Instant's id is what makes the browse dialog draw a message field with a *Say*
    button instead of a list (`browse.py`), and a node that also answered `can_search`
    would be the very two-step search the owner asked to be rid of.
    """
    await _added(hass, aioclient_mock, snapshot())
    root = await hass.services.async_call(
        "media_player",
        "browse_media",
        {"entity_id": PLAYER},
        blocking=True,
        return_response=True,
    )
    children = root[PLAYER].children
    #: The owner's own two words, in the order he asked for them.
    assert [child.title for child in children] == ["menu", "instant"]
    assert [child.can_expand for child in children] == [True, True]
    assert [bool(child.can_search) for child in children] == [True, False]
    assert children[1].media_content_id.startswith("media-source://tts/")

    menu = await hass.services.async_call(
        "media_player",
        "browse_media",
        {"entity_id": PLAYER, "media_content_id": "menu"},
        blocking=True,
        return_response=True,
    )
    #: Empty before a search, but still a legible folder, not a dead end.
    assert menu[PLAYER].children == []
    assert menu[PLAYER].can_search is True

    instant = await hass.services.async_call(
        "media_player",
        "browse_media",
        {"entity_id": PLAYER, "media_content_id": children[1].media_content_id},
        blocking=True,
        return_response=True,
    )
    assert instant[PLAYER].title == "instant"
    assert not instant[PLAYER].can_search


async def test_the_instant_field_plays_the_typed_name_without_searching(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Typed into instant and sent: the show starts, and no list is asked for.

    This is the whole of the card: the browse dialog hands the node's own id back with
    the typed words appended as `message` and `announce` of its own accord (see
    `browse.py`), and that has to reach the serve as the plain query a bare `cast` would
    take - one step, no pick number invented on the way, no `/api/search` at all.
    """
    await _added(hass, aioclient_mock, snapshot())
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


async def test_the_card_shows_a_picture_served_by_the_serve_itself(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """The poster reaches the card, and the address of it stays inside the house.

    The serve downloads the picture and serves it on its own route, so what the entity
    hands Home Assistant is `<base>/api/poster/<name>` and never an address on Wikimedia
    or on a tracker. Home Assistant then proxies it under its own token - which is why
    the attribute the card reads names Home Assistant, not the serve.
    """
    await _added(hass, aioclient_mock, snapshot())
    shown = hass.states.get(PLAYER).attributes

    assert shown["entity_picture"].startswith(f"/api/media_player_proxy/{PLAYER}")
    assert "cache=f34cf352c5ae405a" in shown["entity_picture"]


async def test_home_assistant_takes_the_picture_bytes_from_the_serve_and_no_one_else(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """🔴 The card draws BYTES, and the address they come from has to lead to the serve.

    `entity_picture` proves nothing on its own: Home Assistant builds it out of the hash
    alone, so an entity that names no address at all keeps the very same attribute - and
    the proxy behind it answers a blank picture. Drop `media_image_url` and the card goes
    empty while every attribute stays in place.

    The address asked here is the serve's own route in the LAN. Wikimedia is not asked by
    the client for anything: that traffic would go through the network the product exists
    to step around.
    """
    poster = "/api/poster/06969b7977a4eddd"
    body = b"\xff\xd8\xff\xe0 poster"
    await _added(hass, aioclient_mock, snapshot(image=poster, image_hash="06969b7977a4eddd"))
    aioclient_mock.get(f"{BASE}{poster}", content=body, headers={"Content-Type": "image/jpeg"})
    entity = hass.data[DATA_INSTANCES]["media_player"].get_entity(PLAYER)

    shot, kind = await entity.async_get_media_image()

    assert shot == body
    assert kind == "image/jpeg"
    assert f"{BASE}{poster}" in [str(call[1]) for call in aioclient_mock.mock_calls]


async def test_a_new_show_changes_the_picture_and_not_only_the_title(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """🔴 Without a hash of its own Home Assistant keeps the first picture forever.

    `media_image_hash` is the key it caches the picture by. Leave it at the default (a
    hash of the URL) and a serve that keeps the route stable would show the poster of
    the first film over every film after it: the title on the card would change, the
    picture would not, and nothing anywhere would go red.
    """
    entry = await _added(hass, aioclient_mock, snapshot())
    first = hass.states.get(PLAYER).attributes["entity_picture"]

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE}/api/state",
        json=snapshot(
            title="Тачки", image="/api/poster/367a018cfa600097", image_hash="367a018cfa600097"
        ),
    )
    await entry.runtime_data.async_refresh()
    second = hass.states.get(PLAYER).attributes["entity_picture"]

    assert second != first
    assert "cache=367a018cfa600097" in second


async def test_a_show_without_a_picture_does_not_invent_one(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """A poster that is still being looked for is silence, not a broken picture."""
    await _added(hass, aioclient_mock, snapshot(image=None, image_hash=None))

    assert hass.states.get(PLAYER).attributes.get("entity_picture") is None
