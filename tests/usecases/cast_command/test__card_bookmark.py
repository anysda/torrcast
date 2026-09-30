"""The card's bookmark answers «Play» before the search circle, the circle stays its fallback."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import pytest

import torrcast.usecases.cast_command._card_bookmark as card_bookmark
from tests.fakes import composition
from tests.usecases.cast_command.world import GB, entry
from torrcast.domain.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store.slot import store as watch_store
from torrcast.usecases.cast_command._card_bookmark import _card_bookmark
from torrcast.usecases.cast_command._cmd_play import _cmd_play
from torrcast.usecases.start_clock import _Clock

KEY = "movie:кино:1999"
SERIES = "tv:кино:2008"
STARTED = [[1, 1, 0, GB], [1, 2, 1, GB]]


@pytest.fixture(autouse=True)
def _outside(monkeypatch: pytest.MonkeyPatch) -> None:
    """No receiver passport on the stand: the profile is named directly."""
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "stand"))


@pytest.fixture
def played(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str, float]]:
    """What the early exit started: road, key, recorded magnet and place."""
    seen: list[tuple[str, str, str, float]] = []

    def road(name: str) -> Any:
        def start(_config: Config, key: str, saved: Entry, **_rest: object) -> int:
            seen.append((name, key, saved.magnet, saved.pos))
            return EXIT_OK

        return start

    monkeypatch.setattr(card_bookmark, "_continue", road("continue"))
    monkeypatch.setattr(card_bookmark, "_from_start", road("from_start"))

    def serial(
        _config: Config, state: WatchState, key: str, _title: str, bench: object, **_rest: object
    ) -> int:
        saved = state.get(key)
        assert bench is None, "no bench is warmed for the card's bookmark"
        assert saved is not None
        seen.append(("serial", key, saved.magnet, saved.pos))
        return EXIT_OK

    monkeypatch.setattr(card_bookmark, "_picked_serial", serial)
    return seen


def _remember(key: str, saved: Entry) -> None:
    state = WatchState()
    state.put(key, saved)
    watch_store().save(state)


def _card(*words: str, **rest: Any) -> Args:
    """The args the tab sends for «Play»: the card key, its original and its release."""
    return Args(
        query=["кино", *words],
        picture=rest.pop("picture", KEY),
        card_release="c0ffee",
        here=True,
        **rest,
    )


def _circle() -> tuple[list[Args], Any]:
    asked: list[Args] = []

    def choose(_config: Config, args: Args, *_rest: object) -> int:
        asked.append(args)
        return EXIT_OK

    return asked, choose


def _never(*_args: object, **_rest: object) -> int:
    return pytest.fail("the bookmark knows its release: the circle has nothing to answer")


def test_continue_from_the_card_plays_the_recorded_release_without_the_circle(
    played: list[tuple[str, str, str, float]],
) -> None:
    """🔴 Path A: the bookmark answers before any indexer, so a silent one cannot fail it."""
    _remember(KEY, entry(magnet="magnet:?xt=urn:btih:aa", pos=193.7))

    assert _cmd_play(_card(), choose=_never) == EXIT_OK
    assert played == [("continue", KEY, "magnet:?xt=urn:btih:aa", 193.7)]


def test_a_bookmark_written_by_the_previous_build_resumes_the_same_way(
    played: list[tuple[str, str, str, float]],
) -> None:
    """The record format is unchanged: a record read back from the state file plays as is."""
    before = entry(magnet="magnet:?xt=urn:btih:bb", pos=550.0, file_idx=3, query="кино")
    _remember(KEY, Entry.from_json(json.loads(json.dumps(asdict(before)))))

    assert _cmd_play(_card(), choose=_never) == EXIT_OK
    assert played == [("continue", KEY, "magnet:?xt=urn:btih:bb", 550.0)]


def test_a_started_series_and_start_over_answer_from_the_bookmark_too(
    played: list[tuple[str, str, str, float]],
) -> None:
    """The series door and «Start over» are the same bookmark roads, only earlier."""
    _remember(SERIES, entry(kind="tv", season=1, episode=2, episodes=STARTED))
    assert _cmd_play(_card(picture=SERIES), choose=_never) == EXIT_OK
    assert _cmd_play(_card(picture=SERIES, from_start=True), choose=_never) == EXIT_OK
    assert [road for road, *_ in played] == ["serial", "from_start"]


@pytest.mark.parametrize(
    ("saved", "rest"),
    [
        pytest.param(None, {}, id="no-record"),
        pytest.param(entry(magnet=""), {}, id="record-without-release"),
        pytest.param(entry(pos=0.0), {}, id="nothing-to-continue"),
        pytest.param(entry(done=True), {}, id="finished-film"),
        pytest.param(entry(), {"release": 2}, id="named-release"),
        pytest.param(entry(), {"menu": True}, id="menu"),
        pytest.param(entry(), {"pick": 1}, id="pick-number"),
    ],
)
def test_everything_else_goes_the_circle_way_as_before(
    played: list[tuple[str, str, str, float]], saved: Entry | None, rest: dict[str, Any]
) -> None:
    """No record, no release in it, nothing to continue or a hand-picked road: circle."""
    if saved is not None:
        _remember(KEY, saved)
    asked, choose = _circle()

    assert _cmd_play(_card(**rest), choose=choose) == EXIT_OK
    assert len(asked) == 1 and played == []


def test_a_named_episode_or_a_start_without_a_card_key_is_not_its_business() -> None:
    """A season row names its episode, a spoken query names no key: the old roads answer."""
    state = WatchState()
    state.put(SERIES, entry(kind="tv", season=1, episode=2, episodes=STARTED))
    state.put(KEY, entry())

    for args in (Args(query=["кино", "s1e1"], picture=SERIES), Args(query=["кино"])):
        assert _card_bookmark(Config(), state, args, clock=_Clock()) is None


def test_a_dead_recorded_release_is_buried_and_the_circle_takes_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback: the release no longer plays, the circle picks another and skips it."""
    _remember(KEY, entry(magnet="magnet:?xt=urn:btih:dd"))

    def dead(_config: Config, _key: str, saved: Entry, *, args: Args, **_rest: object) -> None:
        args.bury(saved.magnet)

    monkeypatch.setattr(card_bookmark, "_continue", dead)
    asked, choose = _circle()

    assert _cmd_play(_card(), choose=choose) == EXIT_OK
    assert len(asked) == 1 and asked[0].buried("magnet:?xt=urn:btih:dd")
