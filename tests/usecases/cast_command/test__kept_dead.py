"""Зеркало сохранённого места похороненной раздачи: закладка переживает смену релиза."""

from __future__ import annotations

from tests.usecases.cast_command.world import entry, plan
from torrcast.domain.args import Args
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._kept_dead import _kept_dead

KEY = plan().picture.key


def _state(saved: object | None) -> WatchState:
    state = WatchState()
    if saved is not None:
        state.put(KEY, saved)  # type: ignore[arg-type]
    return state


def _buried(magnet: str = "magnet:?xt=кино") -> Args:
    args = Args(query=["кино"])
    args.bury(magnet)
    return args


def test_the_place_of_a_buried_release_is_kept() -> None:
    """Умирает релиз, а не закладка: место записи доезжает до нового показа."""
    saved = entry(pos=1234.0)

    kept = _kept_dead(_state(saved), KEY, _buried())

    assert kept is not None and kept.pos == 1234.0


def test_a_living_release_keeps_nothing_here() -> None:
    """Никого не хоронили - и держать нечего: обычный путь этой ветки не касается."""
    assert _kept_dead(_state(entry()), KEY, Args(query=["кино"])) is None


def test_a_picture_without_a_bookmark_keeps_nothing() -> None:
    """Записи нет - места нет; выдумывать позицию неоткуда."""
    assert _kept_dead(_state(None), KEY, _buried()) is None


def test_another_release_of_the_same_picture_keeps_nothing() -> None:
    """Похоронен не тот магнит, что записан: место записи к этому отказу отношения не имеет."""
    assert _kept_dead(_state(entry()), KEY, _buried("magnet:?xt=другое")) is None


def test_a_series_carries_its_place_by_episode_and_not_by_seconds() -> None:
    """🔴 У сериала место - пара «серия и позиция», и одной секундой оно не переносится.

    Серию в запрос ставит ``_kept_place``, и место приезжает вместе с ней; голая позиция
    указывала бы внутрь чужой серии, если новый релиз начинается не с той же.
    """
    saved = entry(kind="tv", season=1, episode=2, episodes=[(1, 1), (1, 2)])

    assert _kept_dead(_state(saved), KEY, _buried()) is None
