"""Пометка открытой вкладки, за которой раздачи не дали ни одной играющей серии."""

from __future__ import annotations

from typing import Any, cast

from torrcast.domain.json_value import JsonValue
from web.mark_empty import mark_empty


def _seasons(*rows: tuple[int, int]) -> list[JsonValue]:
    return [
        cast(JsonValue, {"n": number, "episodes": [{"n": index + 1} for index in range(count)]})
        for number, count in rows
    ]


def _marks(seasons: list[JsonValue]) -> list[Any]:
    return [cast(dict[str, Any], season).get("empty") for season in seasons]


def test_the_open_season_without_a_single_episode_is_told_apart_from_the_others() -> None:
    """Метку получает только открытый сезон: соседние пусты, потому что их не разбирали."""
    assert _marks(mark_empty(_seasons((1, 0), (2, 0), (3, 2)), 2, known=True)) == [None, True, None]


def test_a_season_that_holds_episodes_is_never_called_empty() -> None:
    assert _marks(mark_empty(_seasons((1, 0), (2, 3)), 2, known=True)) == [None, None]


def test_a_parse_that_has_not_answered_yet_is_not_an_answer() -> None:
    """Недоехавший разбор это «не знаю»: выдавать его за «нет» нельзя."""
    assert _marks(mark_empty(_seasons((1, 0), (2, 0)), 2, known=False)) == [None, None]


def test_a_season_the_card_does_not_show_at_all_changes_nothing() -> None:
    assert _marks(mark_empty(_seasons((1, 0)), 7, known=True)) == [None]
