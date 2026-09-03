"""Зеркало :mod:`hass.poster_find`: одно правило похода за постером на обоих зовущих."""

from __future__ import annotations

from hass.poster_find import poster_find
from torrcast.domain.facts.ask import Ask

POSTER = b"\xff\xd8\xff\xe0poster"


def test_the_asks_are_tried_in_the_order_they_are_trusted() -> None:
    """Просьбы перебираются по порядку, и найденное первым останавливает перебор."""
    asked: list[str] = []

    def poster(ask: Ask, timeout: float) -> bytes | None:
        asked.append(ask.title)
        return POSTER if ask.title == "Cars" else None

    asks = [Ask("Тачки", 2006, "movie"), Ask("Cars", 2006, "movie"), Ask("тачки", 2006, "movie")]
    assert poster_find(asks, 1.0, poster) == POSTER
    assert asked == ["Тачки", "Cars"]


def test_a_broken_walk_does_not_end_the_search() -> None:
    """Обрыв на одном имени - повод взять следующее, а не ответ «постера нет».

    Отказ сети и картина без английской статьи различаются только следующей попыткой:
    оборвись перебор на первом же имени, исходный запрос не спросили бы никогда.
    """

    def poster(ask: Ask, timeout: float) -> bytes | None:
        if ask.title == "Тачки":
            raise TimeoutError("Википедия не ответила")
        return POSTER

    assert poster_find([Ask("Тачки", 2006, "movie"), Ask("Cars", 2006, "movie")], 1.0, poster) == (
        POSTER
    )


def test_no_asks_means_no_poster() -> None:
    """Спрашивать не о чем - постера нет, и в сеть за ним не ходят."""

    def poster(ask: Ask, timeout: float) -> bytes | None:
        raise AssertionError("за постером пошли, хотя просьб не было")

    assert poster_find([], 1.0, poster) is None
