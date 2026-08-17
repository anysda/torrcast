"""Пересборка плана на настоящей длительности картины, как только её назвала справка."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tests.usecases.reinforce.stand import pictures, row
from torrcast.cli.args import Args
from torrcast.domain.config import Config
from torrcast.domain.facts.fact import Fact
from torrcast.domain.picture import Picture
from torrcast.domain.runtime_guess import RUNTIME_GUESS
from torrcast.usecases.reinforce._plan_for import _plan_for
from torrcast.usecases.reinforce._timed import _timed

#: «Интерстеллар»: у прикидки «фильм это два часа» знаменатель занижен в 1.41 раза.
_INTERSTELLAR = "2 ч 49 мин"


@dataclass
class _Facts:
    """Справка ровно в том объёме, в каком её и спрашивает пересборка плана."""

    runtime: str = ""
    asked: list[tuple[str, int | None]] = field(default_factory=list)

    def get(self, title: str, year: int | None) -> Fact:
        self.asked.append((title, year))
        return Fact(runtime=self.runtime)


def _plan(picture: Picture) -> Any:
    return _plan_for(picture, Args(query=["кино"]), Config())


def _picture() -> Picture:
    return pictures([row("Кино / Movie (1999) BDRip 1080p", "a")])[0]


def test_the_real_runtime_replaces_the_guess_in_the_denominator() -> None:
    """🔴 TC-185. Чинится ЗНАМЕНАТЕЛЬ битрейта, а потолки не двигаются ни на знак."""
    picture = _picture()
    was = _plan(picture)
    facts = _Facts(_INTERSTELLAR)

    fresh = _timed(was, facts, Args(query=["кино"]), Config())

    assert facts.asked == [("Кино", 1999)], "спрашивается та же справка, что и меню"
    assert fresh.runtime == 169 * 60.0 and fresh.runtime_known
    assert fresh.warn_mbit == was.warn_mbit, "потолок остаётся прежним"


def test_a_silent_passport_leaves_the_plan_on_the_guess() -> None:
    """Нет статьи, нет сети, картины нет в выгрузке - план остаётся тем же объектом."""
    was = _plan(_picture())

    assert _timed(was, _Facts(), Args(query=["кино"]), Config()) is was
    assert was.runtime == RUNTIME_GUESS["movie"]


def test_without_facts_at_all_nothing_is_asked() -> None:
    """Справки не было вовсе - пересобирать план не на чем."""
    was = _plan(_picture())

    assert _timed(was, None, Args(query=["кино"]), Config()) is was


def test_the_kin_of_the_old_plan_moves_into_the_fresh_one() -> None:
    """Родня нужна одной строке отказа, и терять её при пересборке нельзя."""
    was = _plan(_picture())
    was.kin = [Picture(title="Соседняя часть", year=2001)]

    fresh = _timed(was, _Facts(_INTERSTELLAR), Args(query=["кино"]), Config())

    assert fresh is not was
    assert [picture.title for picture in fresh.kin] == ["Соседняя часть"]
