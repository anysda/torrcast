"""Почему раздача не доехала до очереди: первая подошедшая причина, а не любая."""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.domain.episode import Episode
from torrcast.domain.release import Release
from torrcast.usecases.rank.drop_reason import drop_reason
from torrcast.usecases.rank.off_season import (
    _codec,
    _disc,
    _extras,
    _heavy,
    _hevc,
    _no_episode,
    _quiet,
    _small,
    _source,
)


@dataclass
class Plan:
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
    assert drop_reason(piece, Plan(want=Episode(1, 5))) == _no_episode()


def test_the_gates_name_the_step_that_threw_the_release_out() -> None:
    plan = Plan()
    assert drop_reason(rel(name="Кино BDMV"), plan) == _disc()
    assert drop_reason(rel(name="Кино: трейлер", size_gb=0.4), plan) == _extras()
    assert drop_reason(rel(size_gb=28), plan) == _heavy()
    assert drop_reason(rel(codec="HEVC"), plan) == _hevc()


def test_the_name_itself_is_the_reason_when_the_gates_did_not_let_it_in() -> None:
    plan = Plan()
    assert drop_reason(rel(codec="MPEG-4"), plan) == _codec()
    assert drop_reason(rel(quality="480p", codec=None), plan) == _small()
    assert drop_reason(rel(quality=None, codec=None, source="WEB-DL"), plan) == _source()
    assert drop_reason(rel(quality=None, codec=None, source=None), plan) == _quiet()


def test_the_receivers_word_takes_hevc_through_without_a_reason() -> None:
    assert drop_reason(rel(codec="HEVC"), Plan(copy_hevc=True)) == ""
    assert drop_reason(rel(codec="HEVC"), Plan(last_resort=True)) == _codec()
