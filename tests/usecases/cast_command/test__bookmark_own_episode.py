"""The row of the bookmark's own episode keeps its place, as the card promises it does."""

from __future__ import annotations

from typing import Any, cast

import pytest

from tests.usecases.cast_command.world import entry, plan
from torrcast.domain.args import Args
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._bookmark import _continue_picked, _plays_recorded
from torrcast.usecases.select._continue import _continue
from torrcast.usecases.start_clock import _Clock

EPISODES = [[1, 4, 0], [1, 5, 1], [1, 6, 2]]


@pytest.fixture(autouse=True)
def _russian(_russian_product: None) -> None:
    """Lines of the show are checked in Russian."""


class _Bench:
    def __init__(self) -> None:
        self.dropped = 0

    def drop_all(self) -> None:
        self.dropped += 1


def _state(pos: float = 61.0, dur: float = 1320.0) -> WatchState:
    state = WatchState()
    saved = entry(kind="tv", season=1, episode=5, pos=pos, dur=dur, episodes=EPISODES)
    state.put(plan().picture.key, saved)
    return state


def _menu(state: WatchState, named: str, capsys: pytest.CaptureFixture[str]) -> tuple[Any, str]:
    code = _continue_picked(
        Config(), state, cast(Any, plan()), _Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино", named], menu=True, dry=True), clock=_Clock(),
    )  # fmt: skip
    return code, capsys.readouterr().out


def test_the_row_of_the_bookmarked_episode_resumes_from_its_place(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Rick and Morty s1e5 promised «Resumes here · 1:01» and played from 0:00 (smoke 30-09)."""
    code, out = _menu(_state(), "s1e5", capsys)

    assert code == 0, out
    assert "s1e5" in out and "0:01:01" in out, out
    assert phrase("bookmark.picked_in_menu", title="Кино", pos="0:01:01") not in out


@pytest.mark.parametrize(
    ("named", "pos"), [("s1e6", 61.0), ("s1e5", 1300.0)], ids=["other", "watched"]
)
def test_another_or_a_watched_episode_still_starts_from_its_beginning(
    named: str, pos: float, capsys: pytest.CaptureFixture[str]
) -> None:
    """Another row has no place of its own, a watched one says «watched»: both start at 0."""
    code, out = _menu(_state(pos), named, capsys)

    assert code is None, out  # the usual path, which starts the episode at 0


def test_a_plain_query_naming_the_bookmarked_episode_keeps_the_place(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``cast кино s1e5`` (Home Assistant sends the episode this way) resumes too."""
    saved = _state().get(plan().picture.key)
    assert saved is not None

    code = _continue(
        Config(), plan().picture.key, saved,
        args=Args(query=["кино", "s1e5"], dry=True), clock=_Clock(),
    )  # fmt: skip

    out = capsys.readouterr().out
    assert code == 0 and "0:01:01" in out, out


@pytest.mark.parametrize(("named", "recorded"), [("s1e5", True), ("s1e6", False)])
def test_the_menu_warm_up_knows_the_bookmark_answers_its_own_episode(
    named: str, recorded: bool
) -> None:
    """The warm-up under the menu asks the same rule, sign for sign."""
    args = Args(query=["кино", named], menu=True)

    assert _plays_recorded(_state(), cast(Any, plan()), args) is recorded
