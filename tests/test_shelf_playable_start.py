"""A shelf verdict begun before a click waits for the show start before reading releases."""

from __future__ import annotations

from typing import Any

from tests.test_shelf_playable import _CONFIG, _PLAN, _alive, _circle
from torrcast.usecases.select.plan import Plan
from web.shelf_playable import ShelfPlayable


def test_the_release_read_waits_for_a_show_start_underway() -> None:
    """Rollback (no gate before the voices): the verdict reads releases during the start."""
    order: list[str] = []

    def voices(_plan: Plan, _query: str, _config: Any) -> tuple[Any, bool, bool]:
        order.append("voices")
        return object(), False, True

    def circle(query: str) -> list[Plan]:
        order.append("circle")
        return [_PLAN] if query else []

    playable = ShelfPlayable(
        circle=circle, voices=voices, alive=_alive, first=lambda: order.append("start first")
    )

    assert playable.of("film", _PLAN.picture.key, _CONFIG) is True
    assert order == ["circle", "start first", "voices"]


def test_an_unranked_plan_does_not_wait_for_the_start() -> None:
    """Nothing to read from TorrServer: a plain «does not play» costs no wait."""
    waited: list[str] = []
    unranked = Plan(picture=_PLAN.picture, ranked=[], runtime=0, warn_mbit=0)
    playable = ShelfPlayable(
        circle=_circle([unranked]),
        voices=lambda *_: (None, False, True),
        alive=_alive,
        first=lambda: waited.append("start first"),
    )

    assert playable.of("film", _PLAN.picture.key, _CONFIG) is False
    assert waited == []
