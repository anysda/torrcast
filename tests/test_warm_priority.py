"""Urgent card circles do not replace or repeat the visible-screen queue."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.warm_cache import WarmCache


def _plan() -> Plan:
    picture = Picture(title="Interstellar", year=2014, kind="movie")
    picture.releases = [Release(raw_name="Interstellar 2014 BDRip", title="Interstellar")]
    return Plan(picture=picture, ranked=picture.releases, runtime=8520.0, warn_mbit=12.0)


def test_an_open_card_runs_before_but_does_not_drop_the_visible_screen() -> None:
    """The card circle gets priority while the screen stays scheduled behind it."""
    jobs: list[Callable[[], None]] = []
    asked: list[str] = []

    def circle(query: str) -> list[Plan]:
        asked.append(query)
        return [_plan()]

    cache = WarmCache(
        circle=circle,
        blurbs=lambda _pictures: None,
        spawn=jobs.append,
    )

    cache.ask(["one", "two"])
    cache.hint("card")
    cache.ask(["one", "two"])
    jobs.pop(0)()

    assert asked == ["card", "one", "two"]
