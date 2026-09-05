"""Сущность медиаплеера: как она называется и что показывает из последнего снимка."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import DATA_INSTANCES

from tests.hass_integration.conftest import BASE, PLAYER, snapshot
from tests.hass_integration.helpers import added


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
    await added(hass, aioclient_mock, snapshot(state=served))
    assert hass.states.get(PLAYER).state == shown


async def test_the_snapshot_becomes_attributes(hass: HomeAssistant, aioclient_mock: Any) -> None:
    """Заголовок, серия, позиция, громкость и хозяйство серве видны на карточке."""
    await added(hass, aioclient_mock, snapshot())
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
    await added(hass, aioclient_mock, snapshot(tv="192.168.1.90"))
    state = hass.states.get("media_player.torrcast_192_168_1_90")
    assert state is not None, "entity_id без приёмника в имени - сущность не найдена"
    assert state.name == "torrcast 192.168.1.90"


async def test_a_second_receiver_gets_its_own_entity(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Другой приёмник в сети - другая сущность, не переезд той же карточки."""
    await added(hass, aioclient_mock, snapshot(tv="192.168.1.91"))
    assert hass.states.get("media_player.torrcast_192_168_1_91") is not None
    assert hass.states.get("media_player.torrcast_192_168_1_90") is None


async def test_a_missing_receiver_does_not_spell_out_none(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Приёмник не найден - карточка называется просто torrcast, не torrcast_none."""
    await added(hass, aioclient_mock, snapshot(tv=None))
    assert hass.states.get("media_player.torrcast") is not None
    assert hass.states.get("media_player.torrcast_none") is None


async def test_empty_fields_do_not_break_the_entity(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Пустым в снимке может быть всё, кроме версии, телевизора и состояния."""
    bare = {"version": "0.99.99", "tv": "TV", "state": "idle"}
    entry = await added(hass, aioclient_mock, bare)
    assert entry.runtime_data.update_interval == timedelta(seconds=30)
    shown = hass.states.get("media_player.torrcast_tv")
    assert shown is not None, "на снимке из пустых полей сущность не завелась вовсе"
    assert shown.state == "idle"
    assert shown.attributes.get("media_title") is None
    assert shown.attributes.get("volume_level") is None


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
    await added(hass, aioclient_mock, snapshot())
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


async def test_the_power_button_bit_is_gone_from_an_empty_screen(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """🔴 TC-1041. Владелец решил оставить в idle одну кнопку: play, не питание.

    Питание гасило бы показ - гасить в idle нечего, а его прежнее дело (продолжить
    последнее с той же секунды) переехало на play. `PLAY` бит снимать не за чем: он
    жил в фиксированном наборе и раньше, только скрытый соседним `TURN_OFF`.
    """
    await added(hass, aioclient_mock, snapshot(state="idle"))
    features = MediaPlayerEntityFeature(hass.states.get(PLAYER).attributes["supported_features"])

    assert MediaPlayerEntityFeature.TURN_OFF not in features
    assert MediaPlayerEntityFeature.PLAY in features


@pytest.mark.parametrize("served", ["starting", "playing", "paused", "torn"])
async def test_the_power_button_bit_stays_everywhere_but_idle(
    hass: HomeAssistant, aioclient_mock: Any, served: str
) -> None:
    """Вне idle показу всегда есть что гасить - бит остаётся заявленным, как раньше."""
    await added(hass, aioclient_mock, snapshot(state=served))
    features = MediaPlayerEntityFeature(hass.states.get(PLAYER).attributes["supported_features"])

    assert MediaPlayerEntityFeature.TURN_OFF in features


async def test_the_power_button_bit_stays_while_the_snapshot_is_still_empty(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Серв ещё не назвал состояние вовсе - это не idle, и бит снимать не с чего.

    `state` читается как `None`, пока в снимке нет самого поля: подожди-ка ещё,
    не «ничего не идёт». Снятый тут бит спрятал бы кнопку раньше, чем серв вообще
    ответил, что показывать нечего.
    """
    await added(hass, aioclient_mock, {"version": "0.99.99", "tv": "192.168.1.90"})
    features = MediaPlayerEntityFeature(hass.states.get(PLAYER).attributes["supported_features"])

    assert MediaPlayerEntityFeature.TURN_OFF in features


async def test_the_right_arrow_stays_on_an_episode_with_a_next_one(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Серия, чья раздача несёт следующий файл: правая стрелка остаётся на карточке."""
    await added(hass, aioclient_mock, snapshot(has_next=True))
    features = MediaPlayerEntityFeature(hass.states.get(PLAYER).attributes["supported_features"])

    assert MediaPlayerEntityFeature.NEXT_TRACK in features


async def test_the_right_arrow_is_gone_from_a_movie_with_no_next_episode(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """🔴 TC-1040. «Не надо показывать стрелку вперёд на фильме - там всё равно нет
    следующего эпизода» (владелец, 04-09-2026): фильма без сезона и серии у раздачи нет
    следующего файла, и правая стрелка карточки об этом узнаёт из `has_next`.
    """
    await added(hass, aioclient_mock, snapshot(has_next=False, season=None, episode=None))
    features = MediaPlayerEntityFeature(hass.states.get(PLAYER).attributes["supported_features"])

    assert MediaPlayerEntityFeature.NEXT_TRACK not in features
    #: Владелец просил снять только мёртвую ПРАВУЮ стрелку; левая («сначала же
    #: серию/фильм») остаётся рабочей и на фильме тоже - её пропажа была бы другим,
    #: более грубым отказом, и проба стережёт его отдельно.
    assert MediaPlayerEntityFeature.PREVIOUS_TRACK in features


async def test_the_right_arrow_is_gone_from_the_last_episode_of_a_series(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """🔴 Тот же отказ, что у фильма, но по другому признаку записи: сезон и серия у
    показа ЕСТЬ, кнопка мертва не потому, что это фильм, а потому что файл в раздаче -
    последний. Проверка стоит на СВОЁМ узле, а не на данных фильма: подмени починку
    условием «вид == фильм», и этот узел покраснеет, а соседний останется зелёным.
    """
    await added(hass, aioclient_mock, snapshot(has_next=False, season=1, episode=9))
    features = MediaPlayerEntityFeature(hass.states.get(PLAYER).attributes["supported_features"])

    assert MediaPlayerEntityFeature.NEXT_TRACK not in features
    assert MediaPlayerEntityFeature.PREVIOUS_TRACK in features


async def test_an_older_serve_without_has_next_keeps_the_arrow(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Мост старее этого поля не присылает `has_next` вовсе: снимок читается как
    «неизвестно», и стрелка остаётся - тот же откат, каким карточка уже читает
    отсутствие `named` (`hass/search_results.py`,
    `custom_components/torrcast/search_media.py`).
    """
    body = snapshot()
    assert "has_next" not in body, "фикстура уже несёт has_next - проба ничего не проверяет"
    await added(hass, aioclient_mock, body)
    features = MediaPlayerEntityFeature(hass.states.get(PLAYER).attributes["supported_features"])

    assert MediaPlayerEntityFeature.NEXT_TRACK in features


async def test_the_right_arrow_stays_between_shows_while_the_next_one_is_unknown(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """В простое и на подъёме мост сам отвечает `has_next: null` (`hass/payload.py`):
    неизвестность не гасит стрелку молча между показами, а держит прежнее поведение.
    """
    await added(hass, aioclient_mock, snapshot(state="idle", has_next=None))
    features = MediaPlayerEntityFeature(hass.states.get(PLAYER).attributes["supported_features"])

    assert MediaPlayerEntityFeature.NEXT_TRACK in features


async def test_the_card_shows_a_picture_served_by_the_serve_itself(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """The poster reaches the card, and the address of it stays inside the house.

    The serve downloads the picture and serves it on its own route, so what the entity
    hands Home Assistant is `<base>/api/poster/<name>` and never an address on Wikimedia
    or on a tracker. Home Assistant then proxies it under its own token - which is why
    the attribute the card reads names Home Assistant, not the serve.
    """
    await added(hass, aioclient_mock, snapshot())
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
    await added(hass, aioclient_mock, snapshot(image=poster, image_hash="06969b7977a4eddd"))
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
    entry = await added(hass, aioclient_mock, snapshot())
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
    await added(hass, aioclient_mock, snapshot(image=None, image_hash=None))

    assert hass.states.get(PLAYER).attributes.get("entity_picture") is None
