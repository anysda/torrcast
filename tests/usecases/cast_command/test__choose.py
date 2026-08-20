"""Зеркало пути до релиза: закладка выбранной картины отвечает показом прямо отсюда."""

from __future__ import annotations

from typing import Any, cast

import pytest

from tests.fakes import composition
from tests.usecases.cast_command.world import entry, plan, plans
from torrcast.domain.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._choose import _choose
from torrcast.usecases.choice._passport import _Passport
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench.bench import Bench
from torrcast.usecases.start_clock import _Clock


class _Facts:
    """Справка, которой нечего сказать: путь до релиза считает по своим числам."""

    def __init__(self, wanted: object) -> None:
        self.wanted = wanted

    def start(self) -> None:
        return None

    def finish(self) -> None:
        return None

    def get(self, *_rest: object) -> Any:
        from torrcast.domain.facts.fact import Fact

        return Fact()


@pytest.fixture(autouse=True)
def _outside(monkeypatch: pytest.MonkeyPatch) -> None:
    """Справка и служба раздач - от корня подделкой; сеть и рой за ними не стоят."""
    composition.use_facts(monkeypatch, _Facts)
    composition.use_engines(monkeypatch, lambda url, timeout=30.0: object())


class _NoBench:
    """Стенд отбора, который ничего не греет: зеркало меряет решение, а не рой."""

    def start(self, plan: object, number: int) -> None:
        return None

    def spare(self, plan: object, args: object) -> None:
        return None

    def drop_all(self) -> None:
        return None


class _NoPassport:
    def get(self) -> Any:
        from torrcast.domain.facts.origin import Origin

        return Origin()


def test_a_saved_place_of_the_chosen_picture_answers_with_a_code() -> None:
    """Закладка выбранной картины отвечает показом сама - и код уезжает наружу целым."""
    state = WatchState()
    state.put(plan().picture.key, entry())

    picked = _choose(
        Config(),
        cast(Any, Args(query=["кино"])),
        Choice(profile=CAUTIOUS, how="стенд"),
        state,
        None,
        _Clock(),
        circle=lambda *args, **rest: [plan()],
        stand=lambda *args, **rest: cast(Bench, _NoBench()),
        passport_of=lambda plans: cast(_Passport, _NoPassport()),
        pick=lambda *args, **rest: plan(),
        bookmark=lambda *args, **rest: EXIT_OK,
    )

    assert picked == EXIT_OK


class _WatchBench:
    """Стенд под наблюдением зеркала: кого попросили греть и у кого попросили запасной."""

    def __init__(self) -> None:
        self.warmed: list[str] = []
        self.spared: list[str] = []

    def start(self, plan: Plan, number: int) -> None:
        self.warmed.append(plan.picture.key)

    def spare(self, plan: Plan, args: object) -> list[object]:
        self.spared.append(plan.picture.key)
        return []

    def drop_all(self) -> None:
        return None


def _continue_by_bookmark(
    state: WatchState, menu: list[Plan], marked: int, bench: _WatchBench
) -> object:
    """Путь продолжения: закладка на части ``marked``, в меню выбрана она же."""
    return _choose(
        Config(),
        cast(Any, Args(query=["тачки"])),
        Choice(profile=CAUTIOUS, how="стенд"),
        state,
        None,
        _Clock(),
        circle=lambda *args, **rest: menu,
        stand=lambda *args, **rest: cast(Bench, bench),
        passport_of=lambda pictures: cast(_Passport, _NoPassport()),
        pick=lambda *args, **rest: menu[marked],
        bookmark=lambda *args, **rest: EXIT_OK,
    )


def test_a_picture_answered_by_its_bookmark_is_not_warmed_under_the_menu() -> None:
    """Картину, за которую ответит закладка, под меню не греют: прогрев снесётся.

    Закладка играет записанную раздачу: выбери человек её - прогретое снесёт она сама,
    выбери соседнюю - уберёт уборка чужих картин. Греть такого кандидата - поднимать
    из роя заведомый мусор, а остальная голова меню греется, как грелась.
    """
    state = WatchState()
    menu = plans(3)
    state.put(menu[0].picture.key, entry(title="Тачки 1"))
    bench = _WatchBench()

    picked = _continue_by_bookmark(state, menu, 0, bench)

    assert picked == EXIT_OK
    assert bench.warmed == [menu[1].picture.key, menu[2].picture.key]
    assert bench.spared == [], "запасной верха меню снесла бы та же закладка"


def test_a_bookmark_off_the_top_keeps_the_warm_of_the_top_and_its_spare() -> None:
    """Закладка на третьей части не мешает греть верх меню и его запасной."""
    state = WatchState()
    menu = plans(3)
    state.put(menu[2].picture.key, entry(title="Тачки 3"))
    bench = _WatchBench()

    picked = _continue_by_bookmark(state, menu, 2, bench)

    assert picked == EXIT_OK
    assert bench.warmed == [menu[0].picture.key, menu[1].picture.key]
    assert bench.spared == [menu[0].picture.key]


def test_the_menu_warm_rises_as_before_when_no_bookmark_answers() -> None:
    """Без закладки голова меню греется вся, как грелась: три части и запасной верха."""
    menu = plans(3)
    bench = _WatchBench()

    picked = _continue_by_bookmark(WatchState(), menu, 0, bench)

    assert picked == EXIT_OK
    assert bench.warmed == [one.picture.key for one in menu]
    assert bench.spared == [menu[0].picture.key]
