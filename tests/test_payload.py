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
        picture=("/api/poster/6b1f", "6b1f"),
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
    assert body["image"] == "/api/poster/6b1f"
    assert body["image_hash"] == "6b1f"
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
        picture=("", ""),
    )
    assert body["season"] is None
    assert body["episode"] is None
    assert body["duration"] is None
    assert body["warm"] is None
    assert body["volume"] is None
    assert body["tv"] is None
    assert body["disk_free"] is None
    assert body["shown_as"] == "Муха"
    # Картинку ещё ищут фоном - и снимок молчит о ней вслух, а не подсовывает пустой
    # адрес: карточка на пустую строку сходила бы за картинкой сама, к себе же в корень.
    assert body["image"] is None
    assert body["image_hash"] is None


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
        picture=("", ""),
    )
    assert body["title"] is None
    assert body["position"] is None
    assert body["last_error"] == "ничего не нашлось"


def test_the_picture_is_named_by_the_serve_and_carries_its_own_fingerprint() -> None:
    """🔴 Отпечаток - не украшение адреса, а ключ смены картинки в карточке.

    ``media_image_hash`` решает у Home Assistant, тянуть ли картинку заново. Уедь он
    пустым (или тем же самым на всех показах) - первая картинка прилипла бы к карточке и
    пережила бы и следующий фильм, и следующую серию: зритель смотрел бы одно, а видел
    рядом другое. Адрес при этом - СВОЙ, серва: наружу за постером карточка не ходит.
    """
    shown = PlaybackSnapshot(key="movie:тачки:2006", title="Тачки", position=1.0, duration=100.0)
    body = payload(
        shown,
        version="1.0.3",
        tv="10.0.1.7",
        state=PLAYING,
        volume=0.4,
        disk_free=10,
        last_error="",
        picture=("/api/poster/2f8c1d", "2f8c1d"),
    )

    assert body["image"] == "/api/poster/2f8c1d"
    assert body["image_hash"] == "2f8c1d"
    assert not str(body["image"]).startswith("http"), "адрес чужого хоста в карточке"
