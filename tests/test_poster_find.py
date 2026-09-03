"""Зеркало :mod:`hass.poster_find`: одно правило похода за постером на обоих зовущих."""

from __future__ import annotations

from hass.poster_find import poster_find

POSTER = b"\xff\xd8\xff\xe0poster"


def test_the_names_are_tried_in_the_order_they_are_trusted() -> None:
    """Имена перебираются по порядку, и найденное первым останавливает перебор."""
    asked: list[str] = []

    def poster(name: str, year: int | None, kind: str, timeout: float) -> bytes | None:
        asked.append(name)
        return POSTER if name == "Cars" else None

    assert poster_find(["Тачки", "Cars", "тачки"], 2006, "movie", 1.0, poster, None) == POSTER
    assert asked == ["Тачки", "Cars"]


def test_a_broken_walk_does_not_end_the_search() -> None:
    """Обрыв на одном имени - повод взять следующее, а не ответ «постера нет».

    Отказ сети и картина без английской статьи различаются только следующей попыткой:
    оборвись перебор на первом же имени, оригинальное название не спросили бы никогда.
    """

    def poster(name: str, year: int | None, kind: str, timeout: float) -> bytes | None:
        if name == "Тачки":
            raise TimeoutError("Википедия не ответила")
        return POSTER

    assert poster_find(["Тачки", "Cars"], 2006, "movie", 1.0, poster, None) == POSTER


def test_the_corrected_name_is_the_last_resort_and_only_with_a_year() -> None:
    """Исправленное справкой имя спрашивается последним - и только когда год известен."""
    asked: list[str] = []

    def poster(name: str, year: int | None, kind: str, timeout: float) -> bytes | None:
        asked.append(name)
        return POSTER if name == "Тачки (мультфильм)" else None

    def correct(name: str, year: int, kind: str, timeout: float) -> str:
        return "Тачки (мультфильм)"

    assert poster_find(["Тачки"], None, "movie", 1.0, poster, correct) is None
    assert asked == ["Тачки"], "без года исправленное имя спрашивать не по чему"
    assert poster_find(["Тачки"], 2006, "movie", 1.0, poster, correct) == POSTER
    assert asked == ["Тачки", "Тачки", "Тачки (мультфильм)"]
