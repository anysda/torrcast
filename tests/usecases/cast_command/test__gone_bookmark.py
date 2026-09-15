"""Строка серии с раздачей закладки, которой нет в выдаче: закладка главнее выдачи."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from tests.usecases.cast_command.world import entry, plan, release
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._bookmark import _continue_picked, _plays_recorded
from torrcast.usecases.cast_command._gone_bookmark import _gone_bookmark
from torrcast.usecases.start_clock import _Clock

_SAVED = "ec1be32af5ebe5a9ea4ebfa115a8b64172a04efd"
_POOLED = "097fd9047fa928346e94ed5c1cb07b9531c15f90"


@pytest.fixture(autouse=True)
def _russian_row(_russian_product: None) -> None:
    """Строки показа русские."""


class _Bench:
    dropped = 0

    def drop_all(self) -> None:
        self.dropped += 1


def _series(magnet: str = _SAVED) -> Any:
    episodes = [(2, 1, 0), (2, 2, 1)]
    return entry(
        kind="tv", season=2, episode=2, episodes=episodes, magnet=f"magnet:?xt=urn:btih:{magnet}"
    )


def _pool(*hashes: str) -> Any:
    own = plan()
    own.picture.releases = [replace(release(), magnet=f"magnet:?xt=urn:btih:{h}") for h in hashes]
    own.ranked = list(own.picture.releases)
    return own


def _row(card: str = _SAVED, **rest: Any) -> Args:
    return Args(query=["кино", "s2e1"], card_release=card, **rest)


def test_a_bookmark_release_gone_from_the_pool_is_played_by_the_bookmark() -> None:
    assert _gone_bookmark(_pool(_POOLED), _series(), _row()) is True


def test_a_pooled_bookmark_release_goes_the_usual_way() -> None:
    """В выдаче она есть: отбор ставит её первой сам, с проверкой ворот."""
    assert _gone_bookmark(_pool(_POOLED, _SAVED), _series(), _row()) is False


def test_another_card_release_or_an_episode_outside_the_bookmark_is_not_the_bookmark() -> None:
    assert _gone_bookmark(_pool(_POOLED), _series(), _row(card=_POOLED)) is False
    outside = Args(query=["кино", "s3e1"], card_release=_SAVED)
    assert _gone_bookmark(_pool(_POOLED), _series(), outside) is False


def test_a_bookmark_release_already_buried_goes_to_the_pool() -> None:
    args = _row()
    args.bury(_series().magnet)
    assert _gone_bookmark(_pool(_POOLED), _series(), args) is False


def test_an_episode_row_plays_the_gone_bookmark_release_at_that_episode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 Раздачи закладки нет в выдаче, и показ играл первую по рангу, переписав закладку."""
    state = WatchState()
    state.put(plan().picture.key, _series())
    bench = _Bench()

    code = _continue_picked(
        Config(), state, _pool(_POOLED), cast(Any, bench), args=_row(dry=True), clock=_Clock()
    )

    assert code == 0
    assert bench.dropped == 1
    assert "s2e1" in capsys.readouterr().out


def test_the_menu_warm_up_skips_the_row_the_gone_bookmark_plays() -> None:
    """Кандидат выдачи такой строки не играет: закладка сама снесёт прогретое."""
    state = WatchState()
    state.put(plan().picture.key, _series())

    assert _plays_recorded(state, _pool(_POOLED), _row()) is True
    assert _plays_recorded(state, _pool(_POOLED, _SAVED), _row()) is False
