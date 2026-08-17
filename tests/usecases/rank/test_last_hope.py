"""Пора ли пускать названный HEVC: живого кандидата нет ВООБЩЕ."""

from __future__ import annotations

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.usecases.rank.last_hope import last_hope

QUIET = {"quality": None, "codec": None, "source": None}


def test_the_last_hope_stays_shut_while_a_live_candidate_can_play() -> None:
    assert not last_hope([rel(seeders=4)], RUNTIME, 20.0)


def test_a_candidate_with_a_dead_swarm_does_not_close_it() -> None:
    """«Гинтама»: DVDRip-AVC на 99 ГБ ворота проходит, а раздаётся нулём пиров."""
    assert last_hope([rel(seeders=0)], RUNTIME, 20.0)


def test_a_live_silent_name_closes_it_only_through_open_gates() -> None:
    quiet = rel(name="Кино (1999)", seeders=3, **QUIET)  # type: ignore[arg-type]
    assert last_hope([quiet], RUNTIME, 20.0)
    assert not last_hope([quiet], RUNTIME, 20.0, loose=True)
