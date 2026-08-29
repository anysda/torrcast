"""Зеркало строки показа: что она несёт в журнал юнита."""

from __future__ import annotations

from torrcast.usecases.screen_line import screen_line


def test_the_line_names_the_place_the_duration_and_the_word_of_the_receiver() -> None:
    """Место, длительность и слово приёмника - всё тремя единицами «ч:мм:сс» и словом."""
    said = screen_line("[сеанс 7]", 26 * 60 + 58.0, 44 * 60.0, "PLAYING")

    assert said == "[сеанс 7] экран: 0:26:58 из 0:44:00 · PLAYING"


def test_the_seconds_go_into_the_line_whole() -> None:
    """Доли секунды в строку не уходят - на них и разбор не рассчитывает."""
    assert screen_line("[с]", 71.9, 120.4, "PAUSED") == "[с] экран: 0:01:11 из 0:02:00 · PAUSED"
