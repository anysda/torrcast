"""Прогрев раздачи карточки: один на процесс, уходит с карточкой, достаётся показу."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

import pytest

import web.card_warm
from torrcast.domain.pick_settings import PICK_BUDGET
from web.card_warm import CardWarm


@dataclass(eq=False)
class _Prep:
    dropped: bool = False
    card_warmed: bool = False


@dataclass(eq=False)
class _Bench:
    profile: str = "cautious"
    choose: str = "card"
    preps: dict[tuple[str, int], _Prep] = field(default_factory=dict)
    kept: list[_Prep] = field(default_factory=list)
    drops: int = 0
    lends: bool = False

    def keep_only(self, prep: _Prep) -> None:
        self.kept.append(prep)

    def drop_all(self) -> None:
        self.drops += 1


class _Line:
    def __init__(self) -> None:
        self.phases: list[str] = []

    def phase(self, text: str) -> None:
        self.phases.append(text)


def _warmed(warms: CardWarm, key: str = "movie:тачки:2006") -> tuple[Any, Any, Any]:
    bench: Any = _Bench()
    prep: Any = _Prep()
    warm, fresh = warms.open(key, lambda: bench)
    assert fresh
    warms.finish(warm, prep)
    return warm, bench, prep


def test_the_chosen_release_stays_warm_until_the_card_is_left() -> None:
    warms = CardWarm()
    _warm, bench, prep = _warmed(warms)

    assert bench.kept == [prep] and prep.card_warmed and bench.drops == 0
    warms.leave("movie:другое:2000")
    assert bench.drops == 0, "чужой уход прогрев не снимает"
    warms.leave("movie:тачки:2006")
    assert bench.drops == 1 and not warms.holds("movie:тачки:2006")


def test_only_the_release_the_card_keeps_is_marked_card_warmed() -> None:
    warms = CardWarm()
    first, _fresh = warms.open("movie:тачки:2006", lambda: cast(Any, _Bench()))
    discarded: Any = _Prep()
    chosen, _fresh = warms.open("movie:вверх:2009", lambda: cast(Any, _Bench()))
    accepted: Any = _Prep()

    warms.finish(first, discarded)
    warms.finish(chosen, accepted)

    assert not discarded.card_warmed and accepted.card_warmed


def test_one_card_at_a_time_a_new_card_takes_the_old_warm_down() -> None:
    warms = CardWarm()
    _warm, first, _prep = _warmed(warms)

    _warmed(warms, "movie:вверх:2009")

    assert first.drops == 1
    assert warms.holds("movie:вверх:2009") and not warms.holds("movie:тачки:2006")


def test_the_show_takes_the_warm_bench_with_its_own_profile_and_without_dropped_releases() -> None:
    warms = CardWarm()
    _warm, bench, prep = _warmed(warms)
    bench.preps = {("k", 1): _Prep(dropped=True), ("k", 2): prep}
    bench.lends = True
    fresh: Any = _Bench(profile="q70d", choose="show")

    got: Any = warms.take("movie:тачки:2006", fresh)

    assert got is bench and (got.profile, got.choose) == ("q70d", "show")
    assert not got.lends, "стенд у показа: срезанное поиском дорожки уходит, как у показа"
    assert list(got.preps.values()) == [prep], "убранную карточкой раздачу показ греет заново"
    warms.leave("movie:тачки:2006")
    assert bench.drops == 0, "стенд у показа: уход с карточки его не трогает"


class _Out(threading.Event):
    """Выход отбора карточки, который случается, пока показ его ждёт."""

    def __init__(self, meanwhile: Callable[[], None]) -> None:
        super().__init__()
        self.meanwhile = meanwhile

    def wait(self, timeout: float | None = None) -> bool:
        self.meanwhile()
        return self.is_set()


def test_a_card_still_choosing_finishes_before_its_bench_goes_to_the_show() -> None:
    warms = CardWarm()
    bench: Any = _Bench()
    warm, _fresh = warms.open("movie:тачки:2006", lambda: bench)
    line = warms.progress(warm, cast(Any, _Line()))
    line.phase("метаданные")
    stopped: list[bool] = []

    def card_choosing() -> None:
        line.phase("дорожки")
        ready: Any = _Prep()
        warms.finish(warm, ready)
        stopped.append(warm.prep is ready)

    warm.out = _Out(card_choosing)

    got: Any = warms.take("movie:тачки:2006", cast(Any, _Bench()))

    assert stopped == [True] and got is bench and bench.drops == 0
    ready: Any = _Prep()
    warms.settled(bench, ready)
    assert warm.chosen.is_set() and warm.prep is ready, "дорожки карточки - от раздачи показа"


def test_a_show_with_nothing_warm_selects_on_its_own_bench_and_a_card_waits_for_it() -> None:
    warms = CardWarm()
    fresh: Any = _Bench()

    assert warms.take("movie:тачки:2006", fresh) is fresh
    warm, opened = warms.open("movie:тачки:2006", cast(Any, _Bench))

    assert opened is False and warm.bench is fresh
    warms.settled(fresh, None)
    assert warm.chosen.is_set() and not warms.holds("movie:тачки:2006")


@pytest.mark.machine
def test_a_card_show_waits_for_the_taken_bench_instead_of_starting_a_second_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Клик ждёт уже начатый отбор, который кончается в пределе, а не заводит второй."""
    monkeypatch.setattr(web.card_warm, "LET_GO", 2.0)
    warms = CardWarm()
    stuck: Any = _Bench()
    warm, _opened = warms.open("movie:тачки:2006", lambda: stuck)
    fresh: Any = _Bench(profile="show")
    taken: list[Any] = []

    caller = threading.Thread(
        target=lambda: taken.append(warms.take("movie:тачки:2006", fresh)), daemon=True
    )
    caller.start()
    caller.join(0.05)

    assert caller.is_alive() and taken == [], "показ подменил идущий отбор своим стендом"
    warms.finish(warm, cast(Any, _Prep()))
    caller.join(1.0)

    assert taken == [stuck] and stuck.drops == 0


@pytest.mark.machine
def test_a_hung_card_selection_holds_the_click_no_longer_than_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Отбор карточки не отпустил стенд к сроку: показ отбирает своим, клик не висит."""
    monkeypatch.setattr(web.card_warm, "LET_GO", 0.1)
    warms = CardWarm()
    stuck: Any = _Bench()
    warm, _opened = warms.open("movie:тачки:2006", lambda: stuck)
    fresh: Any = _Bench(profile="show")
    taken: list[Any] = []

    caller = threading.Thread(
        target=lambda: taken.append(warms.take("movie:тачки:2006", fresh)), daemon=True
    )
    caller.start()
    caller.join(2.0)

    assert taken == [fresh], "клик висит на зависшем отборе карточки"
    warms.finish(warm, cast(Any, _Prep()))
    assert stuck.drops == 1 and stuck.kept == [], "зависший отбор убирает за собой сам"


def test_the_click_waits_for_the_card_selection_as_long_as_the_selection_may_last() -> None:
    """Срок короче потолка отбора заводил бы второй отбор тех же раздач рядом с живым."""
    assert web.card_warm.LET_GO >= PICK_BUDGET
