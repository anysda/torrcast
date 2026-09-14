"""Прогрев раздачи карточки: один на процесс, уходит с карточкой, достаётся показу."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

import pytest

import web.card_warm
from web.card_warm import CardWarm


@dataclass(eq=False)
class _Prep:
    dropped: bool = False


@dataclass(eq=False)
class _Bench:
    profile: str = "cautious"
    choose: str = "card"
    preps: dict[tuple[str, int], _Prep] = field(default_factory=dict)
    kept: list[_Prep] = field(default_factory=list)
    drops: int = 0

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
    fresh: Any = _Bench(profile="q70d", choose="show")

    got: Any = warms.take("movie:тачки:2006", fresh)

    assert got is bench and (got.profile, got.choose) == ("q70d", "show")
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


def test_a_card_still_choosing_is_stopped_and_its_bench_goes_to_the_show() -> None:
    warms = CardWarm()
    bench: Any = _Bench()
    warm, _fresh = warms.open("movie:тачки:2006", lambda: bench)
    line = warms.progress(warm, cast(Any, _Line()))
    line.phase("метаданные")
    stopped: list[bool] = []

    def card_choosing() -> None:
        try:
            line.phase("дорожки")
        except warms.stopped():
            stopped.append(True)
        warms.finish(warm, None)

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


def test_a_card_that_does_not_let_go_leaves_the_show_its_own_bench(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web.card_warm, "LET_GO", 0.01)
    warms = CardWarm()
    stuck: Any = _Bench()
    warm, _opened = warms.open("movie:тачки:2006", lambda: stuck)
    fresh: Any = _Bench()

    assert warms.take("movie:тачки:2006", fresh) is fresh
    warms.finish(warm, cast(Any, _Prep()))

    assert stuck.drops == 1 and stuck.kept == [], "застрявший отбор убирает за собой сам"
