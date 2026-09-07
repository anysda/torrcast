"""Кто из круга отвечает на ключ карточки: :func:`web.card_lookup.card_lookup`."""

from __future__ import annotations

from torrcast.domain.kind import Kind
from torrcast.domain.picture import Picture
from torrcast.usecases.select.plan import Plan
from web.card_lookup import card_lookup


def _plan(title: str, year: int, original: str = "", kind: Kind = "movie") -> Plan:
    picture = Picture(title=title, year=year, kind=kind, original=original or None)
    return Plan(picture=picture, ranked=[], runtime=1.0, warn_mbit=12.0)


def test_a_picture_answers_to_the_key_made_of_its_own_name() -> None:
    plan = _plan("Целиком и полностью", 2022, "Bones and All")

    assert card_lookup([plan], "movie:целиком-и-полностью:2022") == (plan, 1)


def test_a_picture_answers_to_the_key_made_of_its_original_name() -> None:
    """Ключ плитки полки собран из имени раздачи, а круг зовёт картину прокатным."""
    plan = _plan("Целиком и полностью", 2022, "Bones and All")

    assert card_lookup([plan], "movie:bones-and-all:2022") == (plan, 1)


def test_the_number_is_the_place_in_the_circle_not_a_flag() -> None:
    """Номер - то, чем «Играть» просит показ ИМЕННО эту картину (ТЗ §4.3)."""
    first = _plan("Энтони Джесельник: Целиком и полностью", 2024, "Anthony Jeselnik: Bones and All")
    second = _plan("Целиком и полностью", 2022, "Bones and All")

    assert card_lookup([first, second], "movie:bones-and-all:2022") == (second, 2)


def test_a_namesake_in_another_year_keeps_its_own_key() -> None:
    """Второй ключ собран правилом ``Picture.key``, а не поиском имени в строке."""
    plan = _plan("Энтони Джесельник: Целиком и полностью", 2024, "Anthony Jeselnik: Bones and All")

    assert card_lookup([plan], "movie:bones-and-all:2022") == (None, 0)


def test_a_series_does_not_answer_to_a_movie_key() -> None:
    """Род стоит в ключе, и подменять его второй ключ не даёт."""
    plan = _plan("Основание", 2021, "Foundation", kind="tv")

    assert card_lookup([plan], "movie:foundation:2021") == (None, 0)


def test_a_key_nobody_owns_is_no_pick_at_all() -> None:
    plan = _plan("Целиком и полностью", 2022, "Bones and All")

    assert card_lookup([plan], "movie:nobody:1900") == (None, 0)
