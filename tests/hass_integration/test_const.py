"""Имена, общие для интеграции: сроки ожидания и адрес поля мгновенного ввода."""

from __future__ import annotations

from custom_components.torrcast.const import (
    INSTANT_ID,
    INSTANT_TITLE,
    PLAYING,
    POSTER_REQUEST_TIMEOUT,
    REQUEST_TIMEOUT,
    SCAN_INTERVAL_IDLE,
    SCAN_INTERVAL_SHOWING,
    SEARCH_REQUEST_TIMEOUT,
    SHOWING_STATES,
)
from hass.hit_posters import _WAIT
from torrcast.adapters.prowlarr.prowlarr_api import TIMEOUT


def test_the_instant_field_is_addressed_the_way_the_front_end_recognises_it() -> None:
    """🔴 Поле ввода фронт рисует по ПРЕФИКСУ id, а не по флагу.

    `isTTSMediaSource()` шитого фронта смотрит ровно на `media-source://tts/`, и нового
    флага под поле заводить не пришлось. Сменится префикс - поле исчезнет с диалога, а
    дерево обзора останется на месте и промолчит: отсюда проба на самой строке.
    """
    assert INSTANT_ID.startswith("media-source://tts/")
    assert INSTANT_ID.endswith(INSTANT_TITLE)


def test_a_search_waits_out_the_serves_own_ceiling_and_a_state_poll_does_not() -> None:
    """Общий срок на опрос и поиск отказывал по жребию: холодный поиск шёл 11 с.

    Срок поиска считается не от того замера, а от потолка самого серва: он ждёт
    застрявший индексер до `TIMEOUT` секунд, и обрывать его раньше значит выбрасывать
    ответ, который он ещё принесёт.
    """
    assert SEARCH_REQUEST_TIMEOUT > REQUEST_TIMEOUT
    assert SEARCH_REQUEST_TIMEOUT > TIMEOUT


def test_a_poster_waits_out_the_hold_the_serve_keeps_it_under() -> None:
    """Серв держит запрос картинки, вместо того чтобы ответить «нет постера»."""
    assert POSTER_REQUEST_TIMEOUT > _WAIT


def test_a_moving_picture_is_polled_more_often_than_an_empty_screen() -> None:
    """Показ движется, простой - нет; и слово о движении одно на всю интеграцию."""
    assert SCAN_INTERVAL_SHOWING < SCAN_INTERVAL_IDLE
    assert PLAYING in SHOWING_STATES
