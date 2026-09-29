"""Идущий круг под своей строкой: его выдача видна до конца, конец несёт метку полноты."""

from __future__ import annotations

from typing import Any

import pytest

from tests.usecases.discover.world import row
from torrcast.domain.nothing_found_error import NothingFoundError
from torrcast.usecases.discover.circle_watch import CircleWatch, _heard_all
from torrcast.usecases.discover.told_circle import ToldCircle


class _Client:
    def __init__(self, whole: bool | None, rows: int = 0) -> None:
        if whole is not None:
            self.whole = lambda: whole
        self._rows = [row(f"Матрица / The Matrix (1999) BDRip {n}", str(n)) for n in range(rows)]

    def inflight(self) -> list[Any]:
        return list(self._rows)


def test__heard_all_needs_every_client_to_vouch() -> None:
    assert _heard_all([_Client(True), _Client(True)])  # type: ignore[list-item]
    assert not _heard_all([_Client(True), _Client(False)])  # type: ignore[list-item]
    assert not _heard_all([_Client(None)])  # type: ignore[list-item]  # с диска: не доказано
    assert not _heard_all([])


def test_the_plans_carry_the_mark_of_a_whole_catalogue() -> None:
    watch = CircleWatch()

    def circle(hear: Any) -> list[Any]:
        hear(_Client(True))
        return ToldCircle([], [])

    plans = watch.run("матрица", None, circle)
    assert isinstance(plans, ToldCircle) and plans.whole


@pytest.mark.parametrize("vouches", [True, False])
def test_the_nothing_refusal_carries_the_same_mark(vouches: bool) -> None:
    watch = CircleWatch()
    told: list[Any] = []

    def circle(hear: Any) -> list[Any]:
        hear(_Client(vouches))
        raise NothingFoundError("пусто")

    with pytest.raises(NothingFoundError) as caught:
        watch.run("матрица", told.append, circle)
    assert caught.value.whole is vouches
    assert len(told) == 1, "шов превью слышит клиента, как и прежде"


def test_rows_are_seen_while_the_circle_runs_and_gone_after() -> None:
    watch = CircleWatch()
    seen: list[Any] = []

    def circle(hear: Any) -> list[Any]:
        hear(_Client(True, rows=3))
        seen.append(watch.rows(" матрица "))  # круг ещё идёт: его спрашивает превью
        return ToldCircle([], [])

    watch.run("матрица", None, circle)
    raw, named, known = seen[0]
    assert len(raw) == 3 and named == [] and known is None
    assert watch.rows("матрица") == ([], [], None)


def test_two_circles_of_one_line_leave_one_by_one() -> None:
    """Два пустых списка равны, но кругов два: конец одного не снимает другой."""
    watch = CircleWatch()
    with watch.watching("q") as first, watch.watching("q") as second:
        assert first is not second
        second.append(_Client(True, rows=2))  # type: ignore[arg-type]
    with watch.watching("q") as first:
        with watch.watching("q") as second:
            second.append(_Client(True, rows=2))  # type: ignore[arg-type]
        assert watch.rows("q") == ([], [], None)
        first.append(_Client(True, rows=1))  # type: ignore[arg-type]
        assert len(watch.rows("q")[0]) == 1


def test_one_release_sent_by_two_indexers_is_counted_once() -> None:
    """Круг клеит одну раздачу разных индексеров в одну, и счёт до конца круга тоже."""
    watch = CircleWatch()
    with watch.watching("q") as heard:
        heard += [_Client(True, rows=2), _Client(True, rows=3)]  # type: ignore[list-item]
        assert len(watch.rows("q")[0]) == 3


def test_the_pool_the_circle_took_is_counted_while_it_runs() -> None:
    """A late tail or a reinforcement enters the count once the circle keeps it, not before."""
    watch = CircleWatch()
    seen: list[int] = []
    kept = [row(f"Матрица / The Matrix (1999) BDRip {n}", str(n)) for n in range(4)]

    def circle(hear: Any) -> list[Any]:
        hear(_Client(True, rows=2))
        seen.append(len(watch.rows("матрица")[0]))
        watch.keep(kept)  # two of these the first row already sent
        seen.append(len(watch.rows("матрица")[0]))
        return ToldCircle([], [])

    watch.run("матрица", None, circle)
    watch.keep(kept)  # no circle runs here: nothing to keep it for
    assert seen == [2, 4]
    assert watch.rows("матрица") == ([], [], None)
