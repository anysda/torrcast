"""Почему раздача не доехала до очереди: первая подошедшая причина, а не любая."""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.domain.episode import Episode
from torrcast.domain.release import Release
from torrcast.usecases.rank.drop_reason import drop_reason
from torrcast.usecases.rank.drop_reasons import (
    _CODEC,
    _DISC,
    _EXTRAS,
    _HEAVY,
    _HEVC,
    _NO_EPISODE,
    _QUIET,
    _SMALL,
    _SOURCE,
)


@dataclass
class _Plan:
    """Ровно то, что правило у плана и спрашивает."""

    ranked: list[Release] = field(default_factory=list)
    want: Episode | None = None
    runtime: float = RUNTIME
    warn_mbit: float = 20.0
    hard_mbit: float = 0.0
    copy_hevc: bool = False
    last_resort: bool = False


def test_the_missing_episode_is_judged_before_everything_else() -> None:
    piece = rel(name="огрызок BDMV", kind="tv", seasons=(1,), episodes=(1,))
    assert drop_reason(piece, _Plan(want=Episode(1, 5))) == _NO_EPISODE


def test_the_gates_name_the_step_that_threw_the_release_out() -> None:
    plan = _Plan()
    assert drop_reason(rel(name="Кино BDMV"), plan) == _DISC
    assert drop_reason(rel(name="Кино: трейлер", size_gb=0.4), plan) == _EXTRAS
    assert drop_reason(rel(size_gb=28), plan) == _HEAVY
    assert drop_reason(rel(codec="HEVC"), plan) == _HEVC


def test_the_name_itself_is_the_reason_when_the_gates_did_not_let_it_in() -> None:
    plan = _Plan()
    assert drop_reason(rel(codec="MPEG-4"), plan) == _CODEC
    assert drop_reason(rel(quality="480p", codec=None), plan) == _SMALL
    assert drop_reason(rel(quality=None, codec=None, source="WEB-DL"), plan) == _SOURCE
    assert drop_reason(rel(quality=None, codec=None, source=None), plan) == _QUIET


def test_the_receivers_word_takes_hevc_through_without_a_reason() -> None:
    assert drop_reason(rel(codec="HEVC"), _Plan(copy_hevc=True)) == ""
    assert drop_reason(rel(codec="HEVC"), _Plan(last_resort=True)) == _CODEC
