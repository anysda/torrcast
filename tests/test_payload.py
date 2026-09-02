"""Зеркало снимка показа: что мост говорит карточке плеера и о чём молчит."""

from __future__ import annotations

import json

from hass.motion import IDLE, PLAYING
from hass.payload import payload
from torrcast.domain.playback_snapshot import PlaybackSnapshot


def test_full_snapshot_becomes_json_the_card_can_draw() -> None:
    shown = PlaybackSnapshot(
        key="series:чернобыль:2019",
        title="Чернобыль",
        position=1234.56,
        duration=3600.0,
        label="s1e3",
        warm=1800.0,
    )
    body = payload(
        shown,
        version="1.0.3",
        tv="10.0.1.7",
        state=PLAYING,
        volume=0.42,
        disk_free=1234,
        last_error="",
    )
    assert body["state"] == PLAYING
    assert body["title"] == "Чернобыль"
    assert body["shown_as"] == "Чернобыль s1e3"
    assert body["season"] == 1
    assert body["episode"] == 3
    assert body["position"] == 1234.6
    assert body["duration"] == 3600.0
    assert body["warm"] == 50
    assert body["volume"] == 0.42
    assert body["tv"] == "10.0.1.7"
    assert body["last_error"] is None
    # Тело уезжает по HTTP, а не остаётся объектом: несериализуемое поле сломало бы
    # карточку уже у зрителя, а не тут.
    assert json.loads(json.dumps(body)) == body


def test_holey_snapshot_says_null_and_does_not_invent_numbers() -> None:
    # Фильм без подписи серии и с неизвестной длительностью: сезона, серии, доли
    # прогрева и остатка диска взять неоткуда.
    shown = PlaybackSnapshot(key="movie:муха:1986", title="Муха", position=0.0)
    body = payload(
        shown,
        version="1.0.3",
        tv="",
        state=PLAYING,
        volume=None,
        disk_free=0,
        last_error="",
    )
    assert body["season"] is None
    assert body["episode"] is None
    assert body["duration"] is None
    assert body["warm"] is None
    assert body["volume"] is None
    assert body["tv"] is None
    assert body["disk_free"] is None
    assert body["shown_as"] == "Муха"


def test_idle_does_not_answer_with_the_picture_that_already_ended() -> None:
    # Прошлый показ кончился, а снимок на диске остался: карточка не вправе рисовать
    # его как идущий - иначе зритель видит на экране кино, которого нет.
    shown = PlaybackSnapshot(key="movie:муха:1986", title="Муха", position=60.0, duration=300.0)
    body = payload(
        shown,
        version="1.0.3",
        tv="10.0.1.7",
        state=IDLE,
        volume=0.5,
        disk_free=10,
        last_error="ничего не нашлось",
    )
    assert body["title"] is None
    assert body["position"] is None
    assert body["last_error"] == "ничего не нашлось"
