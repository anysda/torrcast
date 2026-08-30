"""Зеркало отказа молчащего роя: пять разных строк, и различают их счётчики, а не догадка."""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import franchise, row
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover.silent_swarm import silent_swarm
from torrcast.usecases.reinforce.plan_for import plan_for
from torrcast.usecases.select.plan import Plan


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - пять русских строк отказа молчащего роя."""


_SHOWN = "показывали «кино»"


def _plan(rows: list[RawResult], query: str = "тачки") -> Plan:
    return plan_for(franchise(query, rows)[0], Args(query=[query]), Config())


def _rows(*seeders: int) -> list[RawResult]:
    return [
        row(f"Тачки / Cars (2006) BDRip 1080p {n}", chr(97 + n), size_gb=5.0, seeders=seed)
        for n, seed in enumerate(seeders)
    ]


def test_a_swarm_without_a_single_seeder_is_named_as_it_is() -> None:
    """Сидов не числится ни у одной раздачи - «пиров нет» тут сказано честно."""
    plan = _plan(_rows(0, 0))

    line = silent_swarm(plan, [1, 2], 2, _SHOWN)

    assert "пиров нет ни у одной" in line
    assert "выбери руками" not in line, "выбирать не из чего - ход другой"


def test_a_walk_cut_by_the_clock_names_what_was_left_unasked() -> None:
    """🔴 TC-435. Обход кончился часами, а не очередью: хвост не спрашивали вовсе."""
    plan = _plan(_rows(50, 40, 30))

    line = silent_swarm(plan, [1, 2, 3], 1, _SHOWN)

    assert "из очереди 3" in line
    assert "на остальных не хватило времени" in line


def test_touching_everything_is_the_silence_of_the_swarm() -> None:
    """Потрогали всю выдачу - молчат все, кого можно было спросить, а сиды числились."""
    plan = _plan(_rows(50, 40))

    line = silent_swarm(plan, [1, 2], 2, _SHOWN)

    assert "(все) - ни одна не отозвалась" in line
    assert "до 50" in line, "сиды называются как обещание индексера, а не как факт"


def test_untouched_and_usable_leaves_the_human_a_manual_choice() -> None:
    """Нетронутое есть и оно пригодно - врать за него нельзя, ход человеку остаётся."""
    plan = _plan(_rows(50, 40, 30))

    line = silent_swarm(plan, [1], 1, _SHOWN)

    assert "до остальных отбор не дошёл" in line
    assert "выбери руками" in line


def test_naming_a_release_turns_the_manual_choice_into_another_one() -> None:
    """Релиз человек назвал сам - ход у него уже не «выбери», а «выбери другой»."""
    plan = _plan(_rows(50, 40, 30))

    line = silent_swarm(plan, [1], 1, _SHOWN, picked=1)

    assert "выбери другой релиз" in line
