"""Кто из круга отвечает на ключ карточки: :func:`web.card_lookup.card_lookup`."""

from __future__ import annotations

from torrcast.domain.kind import Kind
from torrcast.domain.picture import Picture
from torrcast.usecases.select.plan import Plan
from web.card_lookup import card_lookup


def _plan(
    title: str,
    year: int,
    original: str = "",
    kind: Kind = "movie",
    also: str = "",
    aliases: tuple[str, ...] = (),
) -> Plan:
    picture = Picture(
        title=title, year=year, kind=kind, original=original or None, also=also, aliases=aliases
    )
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


def test_a_picture_answers_to_the_key_made_of_the_name_the_feed_gave_it() -> None:
    """Плитка полки зовёт картину именем ленты раздач, а круг - именем каталога.

    Замер на стенде `.104` 07-09-2026: круг по запросу «Better Days» отдаёт картину
    ``title="Лучшие дни"``, ``original="Shao nian de ni"``, ``also="Better Days"``,
    ``aliases=("better-days",)`` - и ни одно из двух своих имён не даёт ключа полки.
    """
    plan = _plan(
        "Лучшие дни", 2019, "Shao nian de ni", also="Better Days", aliases=("better-days",)
    )

    assert card_lookup([plan], "movie:better-days:2019") == (plan, 1)


def test_a_namesake_with_the_same_alias_in_another_year_is_another_picture() -> None:
    """Год стоит в ключе, и одного алиаса на двоих мало: тот же замер отдал вторым
    номером «Лучшие дни» 2025 года с тем же ``better-days`` в алиасах."""
    older = _plan(
        "Лучшие дни", 2019, "Shao nian de ni", also="Better Days", aliases=("better-days",)
    )
    newer = _plan("Лучшие дни", 2025, "Des jours meilleurs", aliases=("better-days",))

    assert card_lookup([newer, older], "movie:better-days:2019") == (older, 2)
