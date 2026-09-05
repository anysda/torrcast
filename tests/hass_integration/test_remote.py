"""Кнопки карточки: что уходит на серве по каждой и как читается отказ."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from tests.hass_integration.conftest import BASE, PLAYER, sent, snapshot
from tests.hass_integration.helpers import added


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
    await added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(f"{BASE}{path}", status=204)
    await hass.services.async_call(
        "media_player", service, {"entity_id": PLAYER, **extra}, blocking=True
    )
    posted = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert len(posted) == 1
    assert str(posted[0][1]) == f"{BASE}{path}"
    assert sent(posted[0]) == body


async def test_turning_off_an_empty_screen_carries_on_the_last_show(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Гасить нечего - та же кнопка поднимает последнее смотренное, как пустой `cast`.

    Одна кнопка на две просьбы: пока идёт показ, она его гасит, а на пустом экране
    отвечает на «включи то, что я смотрел». Останавливать тут нечего, и `stop` серве
    отбил бы `nothing_playing` - отказом, который человеку читается как поломка.

    Своего правила интеграция не заводит: она зовёт маршрут продолжения, а картину и
    секунду называет продукт. Поэтому проверяется и адрес, и ПУСТОЕ тело: имя картины,
    подставленное тут, было бы вторым ответом на тот же вопрос.
    """
    await added(hass, aioclient_mock, snapshot(state="idle"))
    aioclient_mock.post(f"{BASE}/api/resume", status=202, json={"key": "cafebabe"})
    told: list[str] = []

    try:
        await hass.services.async_call(
            "media_player", "turn_off", {"entity_id": PLAYER}, blocking=True
        )
    except HomeAssistantError as refusal:
        told.append(str(refusal))

    assert told == [], f"человеку показали отказ на нажатие «выключить»: {told}"
    posted = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert [str(call[1]) for call in posted] == [f"{BASE}/api/resume"]
    assert [sent(call) for call in posted] == [None]


async def test_turning_off_a_torn_show_leads_the_person_out_instead_of_refusing(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """🔴 TC-1022. Кнопка выключения на залипшем показе - дверь наружу, а не отказ.

    Живой замер 03-09-2026: подъём умер молча, карточка встала в `torn`, и нажатие
    «выключить» отвечало `HomeAssistantError: torrcast is already starting a show`.
    Серве больше не отказывает в остановке ничем, и кнопка обязана этой дверью
    воспользоваться: `torn` - это не `idle`, молчать ей тут не с чего.
    """
    await added(hass, aioclient_mock, snapshot(state="torn"))
    aioclient_mock.post(f"{BASE}/api/control", status=204)
    told: list[str] = []

    try:
        await hass.services.async_call(
            "media_player", "turn_off", {"entity_id": PLAYER}, blocking=True
        )
    except HomeAssistantError as refusal:
        told.append(str(refusal))

    assert told == [], f"человеку показали отказ на нажатие «выключить»: {told}"
    posted = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert [sent(call) for call in posted] == [{"cmd": "stop"}]


async def test_a_refusal_becomes_a_readable_failure(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """409 от серве доходит до человека словами, а состояние остаётся прежним."""
    await added(hass, aioclient_mock, snapshot())
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
    await added(hass, aioclient_mock, snapshot(volume=None))
    with pytest.raises(HomeAssistantError, match="volume"):
        await hass.services.async_call(
            "media_player", "volume_up", {"entity_id": PLAYER}, blocking=True
        )
    assert not [call for call in aioclient_mock.mock_calls if call[0] == "POST"]


async def test_a_restart_without_a_known_position_is_refused(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """«Сначала» не от чего отмотать без известной позиции: отказ словами, не исключение."""
    await added(hass, aioclient_mock, snapshot(position=None))
    with pytest.raises(HomeAssistantError, match="current position"):
        await hass.services.async_call(
            "media_player", "media_previous_track", {"entity_id": PLAYER}, blocking=True
        )
    assert not [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
