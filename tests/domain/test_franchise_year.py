"""Checks that the year a query named narrows the franchise its name found."""

from __future__ import annotations

from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture

_GHOST = [
    Picture("Призрак в доспехах", 1995),
    Picture("Призрак в доспехах: Синдром одиночки", 2006),
    Picture("Призрак в доспехах", 2026, "tv"),
]


def _years(query: str) -> list[int | None]:
    return [p.year for p in pick_franchise(query, _GHOST)]


def test_the_year_named_leaves_its_picture_alone() -> None:
    assert _years("Призрак в доспехах 2026") == [2026]


def test_no_year_or_a_year_not_found_keeps_the_franchise() -> None:
    assert _years("Призрак в доспехах") == [1995, 2006, 2026]
    assert _years("Призрак в доспехах 2031") == [1995, 2006, 2026]
