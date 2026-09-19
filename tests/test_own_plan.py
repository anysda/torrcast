"""Своя строка картины, а не та, которой её открыли: :func:`web.own_plan.own_plan`."""

from __future__ import annotations

import pytest

from torrcast.domain.nothing_found_error import NothingFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.usecases.select.plan import Plan
from web.own_plan import Circle, own_plan

_PICTURE = Picture(title="Призрак в доспехах", year=2026, kind="tv")
_PLAN = Plan(picture=_PICTURE, ranked=[], runtime=1.0, warn_mbit=12.0)
_KEY = _PICTURE.key


def _circle(by_query: dict[str, list[Plan]]) -> tuple[list[str], Circle]:
    """Круг-подмена: помнит, какими строками его спросили, и отвечает по словарю."""
    asked: list[str] = []

    def circle(query: str) -> list[Plan]:
        asked.append(query)
        if query in by_query:
            return by_query[query]
        raise NothingFoundError(f"ничего не нашлось по «{query}»")

    return asked, circle


def test_the_own_title_finds_the_picture_a_truncated_search_string_missed() -> None:
    """Случай владельца TC-1334: набор оборвался («...-202» вместо «...-2026»)."""
    asked, circle = _circle({"призрак в доспехах": [_PLAN]})

    plan, pick, found = own_plan(_KEY, "призрак-в-доспехах-202", "призрак в доспехах", circle)

    assert (plan, pick, found) == (_PLAN, 1, "призрак в доспехах")
    assert asked == ["призрак-в-доспехах-202", "призрак в доспехах"]


def test_an_empty_query_still_finds_the_picture_by_its_title() -> None:
    """Прямая ссылка на карточку без строки поиска: ``query`` пуст, ``title`` цел."""
    asked, circle = _circle({"призрак в доспехах": [_PLAN]})

    plan, pick, found = own_plan(_KEY, "", "призрак в доспехах", circle)

    assert (plan, pick, found) == (_PLAN, 1, "призрак в доспехах")
    assert asked == ["призрак в доспехах"]


def test_a_stranger_pictures_query_still_finds_the_right_one_by_title() -> None:
    """Родня или история завели карточку чужой строкой - своё имя всё равно находит."""
    asked, circle = _circle({"призрак в доспехах": [_PLAN]})

    plan, pick, found = own_plan(_KEY, "матрица", "призрак в доспехах", circle)

    assert (plan, pick, found) == (_PLAN, 1, "призрак в доспехах")
    assert asked == ["матрица", "призрак в доспехах"]


def test_a_bare_link_with_no_facts_at_all_still_resolves_from_the_key() -> None:
    """Ни ``query``, ни ``title`` не пришли вовсе - последний довод восстановлен из ключа."""
    asked, circle = _circle({"призрак в доспехах": [_PLAN]})

    plan, pick, found = own_plan(_KEY, "", "", circle)

    assert (plan, pick, found) == (_PLAN, 1, "призрак в доспехах")
    assert asked == ["призрак в доспехах"]


def test_the_first_working_string_stops_the_search_there() -> None:
    """Рабочий запрос не платит вторым и третьим кругом: он у карточки уже есть."""
    asked, circle = _circle({"призрак в доспехах": [_PLAN]})

    own_plan(_KEY, "призрак в доспехах", "призрак в доспехах", circle)

    assert asked == ["призрак в доспехах"]


def test_a_named_refusal_is_not_retried_with_another_string() -> None:
    """Именной отказ круга (Prowlarr не настроен и т.п.) общий на все попытки."""

    def circle(_query: str) -> list[Plan]:
        raise TorrcastError("не настроен Prowlarr")

    with pytest.raises(TorrcastError, match="не настроен Prowlarr"):
        own_plan(_KEY, "призрак-в-доспехах-202", "призрак в доспехах", circle)


def test_nothing_found_by_any_string_raises_the_last_silent_refusal() -> None:
    """Картины и правда нет ни по одному имени - ответ молчаливый, как и у поиска."""

    def circle(query: str) -> list[Plan]:
        raise NothingFoundError(f"ничего не нашлось по «{query}»")

    with pytest.raises(NothingFoundError):
        own_plan(_KEY, "призрак-в-доспехах-202", "призрак в доспехах", circle)


def test_a_query_that_finds_someone_elses_circle_without_erroring_still_falls_through() -> None:
    """Строка не пуста и круг непуст, но своей картины среди них нет - пробуем дальше."""
    other = Picture(title="Матрица", year=1999, kind="movie")
    other_plan = Plan(picture=other, ranked=[], runtime=1.0, warn_mbit=12.0)
    asked, circle = _circle(
        {"матрица": [other_plan], "призрак в доспехах": [_PLAN]}
    )

    plan, pick, found = own_plan(_KEY, "матрица", "призрак в доспехах", circle)

    assert (plan, pick, found) == (_PLAN, 1, "призрак в доспехах")
    assert asked == ["матрица", "призрак в доспехах"]
