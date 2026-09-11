"""Зеркало продолжения сериала, выбранного в меню: серия и секунда закладки, а не s1e1."""

from __future__ import annotations

import pytest

from tests.usecases.cast_command.world import entry, plan
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._picked_serial import _picked_serial
from torrcast.usecases.start_clock import _Clock

KEY = plan().picture.key


class _Bench:
    def __init__(self) -> None:
        self.dropped = 0

    def drop_all(self) -> None:
        self.dropped += 1


def _state(saved: object | None) -> WatchState:
    state = WatchState()
    if saved is not None:
        state.put(KEY, saved)  # type: ignore[arg-type]
    return state


@pytest.fixture(autouse=True)
def _russian(_russian_product: None) -> None:
    """Строки показа сверяются по-русски."""


def test_a_started_series_plays_the_bookmarked_episode_from_its_second(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-1203. «Играть» веба у «Отчаянных домохозяек» играло s1e1 с нуля вместо s3e14."""
    saved = entry(kind="tv", season=3, episode=14, pos=546.0, episodes=[(3, 13), (3, 14)])
    bench = _Bench()

    code = _picked_serial(
        Config(), _state(saved), KEY, "Кино", bench,  # type: ignore[arg-type]
        args=Args(query=["кино"], pick=1, dry=True), clock=_Clock(),
    )  # fmt: skip

    out = capsys.readouterr().out
    assert code == 0
    assert "s3e14" in out and "0:09:06" in out, out
    assert bench.dropped == 1


def test_a_picture_without_a_bookmark_goes_the_usual_way() -> None:
    """Записи нет - серию выберет обычный путь; про s1e1 решает он, а не закладка."""
    code = _picked_serial(
        Config(), _state(None), KEY, "Кино", _Bench(),  # type: ignore[arg-type]
        args=Args(query=["кино"], pick=1, dry=True), clock=_Clock(),
    )  # fmt: skip

    assert code is None


def test_a_dead_release_hands_its_episode_to_the_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """Раздача закладки не играется - ищем другую, но ТУ ЖЕ серию, а не первую."""
    saved = entry(kind="tv", season=3, episode=14, pos=546.0, episodes=[(3, 13), (3, 14)])
    args = Args(query=["кино"], pick=1, dry=True)

    def dead(config: Config, key: str, found: object, *, args: Args, clock: _Clock) -> None:
        args.bury(saved.magnet)  # как :func:`_continue`, признавший раздачу мёртвой

    monkeypatch.setattr("torrcast.usecases.cast_command._picked_serial._continue", dead)

    code = _picked_serial(
        Config(), _state(saved), KEY, "Кино", _Bench(),  # type: ignore[arg-type]
        args=args, clock=_Clock(),
    )  # fmt: skip

    assert code is None
    assert args.query[-1] == "s3e14", args.query
