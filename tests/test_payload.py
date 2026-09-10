"""Зеркало снимка показа: что мост говорит карточке плеера и о чём молчит."""

from __future__ import annotations

import json

from hass.motion import IDLE, PLAYING, STARTING
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
        build="abc123def456",
        tv="10.0.1.7",
        state=PLAYING,
        volume=0.42,
        disk_free=1234,
        last_error="",
        picture=("/api/poster/6b1f", "6b1f"),
        has_next=True,
    )
    assert body["state"] == PLAYING
    assert body["build"] == "abc123def456"
    assert body["has_next"] is True
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
        build="abc123def456",
        tv="",
        state=PLAYING,
        volume=None,
        disk_free=0,
        last_error="",
        picture=("", ""),
        has_next=False,
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
    # Фильм: следующей серии в раздаче нет, и стрелка вперёд об этом узнаёт отсюда же.
    assert body["has_next"] is False


def test_idle_does_not_answer_with_the_picture_that_already_ended() -> None:
    # Прошлый показ кончился, а снимок на диске остался: карточка не вправе рисовать
    # его как идущий - иначе зритель видит на экране кино, которого нет.
    shown = PlaybackSnapshot(key="movie:муха:1986", title="Муха", position=60.0, duration=300.0)
    body = payload(
        shown,
        version="1.0.3",
        build="abc123def456",
        tv="10.0.1.7",
        state=IDLE,
        volume=0.5,
        disk_free=10,
        last_error="ничего не нашлось",
        picture=("", ""),
        has_next=True,
    )
    assert body["title"] is None
    assert body["position"] is None
    assert body["last_error"] == "ничего не нашлось"
    # В простое про следующую серию сказать нечего: стрелка ни явно есть, ни явно
    # снята - интеграция читает ``null`` как «не гасить её молча между показами»
    # (:meth:`custom_components.torrcast.player.Player.supported_features`), даже если
    # сам мост уже знает ответ (тут - ``True``).
    assert body["has_next"] is None


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
        build="abc123def456",
        tv="10.0.1.7",
        state=PLAYING,
        volume=0.4,
        disk_free=10,
        last_error="",
        picture=("/api/poster/2f8c1d", "2f8c1d"),
        has_next=False,
    )

    assert body["image"] == "/api/poster/2f8c1d"
    assert body["image_hash"] == "2f8c1d"
    assert not str(body["image"]).startswith("http"), "адрес чужого хоста в карточке"


def test_an_unknown_build_says_so_instead_of_a_made_up_value() -> None:
    """Клейма нет и не у кого спросить (тарбол без git) - ``null``, а не выдумка."""
    shown = PlaybackSnapshot(key="movie:муха:1986", title="Муха", position=0.0)
    body = payload(
        shown,
        version="1.0.3",
        build=None,
        tv="",
        state=PLAYING,
        volume=None,
        disk_free=0,
        last_error="",
        picture=("", ""),
        has_next=False,
    )
    assert body["build"] is None
    # Номер выпуска остаётся: то, что клейма нет, не отменяет уже существующего
    # договора с интеграцией (custom_components/torrcast/serve_client.py).
    assert body["version"] == "1.0.3"


def test_the_lift_in_progress_reaches_the_one_waiting_at_the_screen() -> None:
    """Пока картинки нет, снимок несёт срок ожидания и номер источника очереди.

    Экран подготовки (`web/static/player-screens.js`) другого источника числа не имеет:
    посчитанная на стороне страницы секунда была бы выдумкой. Подъёма нет - поле пустое,
    и страница рисует подготовку без числа, ровно как до этого поля.
    """
    shown = PlaybackSnapshot(key="movie:муха:1986", title="Муха", position=0.0)
    lifting = payload(
        shown,
        version="1.0.3",
        build="abc123def456",
        tv="",
        state=STARTING,
        volume=None,
        disk_free=0,
        last_error="",
        picture=("", ""),
        has_next=False,
        start={"waited": 12.0, "left": 18, "source": 2, "sources": 5},
    )
    assert lifting["start"] == {"waited": 12.0, "left": 18, "source": 2, "sources": 5}
    assert json.loads(json.dumps(lifting)) == lifting

    quiet = payload(
        shown,
        version="1.0.3",
        build="abc123def456",
        tv="",
        state=PLAYING,
        volume=None,
        disk_free=0,
        last_error="",
        picture=("", ""),
        has_next=False,
    )
    assert quiet["start"] is None
