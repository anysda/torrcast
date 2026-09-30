"""Почему раздача не доехала до очереди: первая подошедшая причина, а не любая."""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.rank.drop_reason import drop_reason
from torrcast.usecases.rank.off_season import (
    _codec,
    _disc,
    _extras,
    _heavy,
    _hevc,
    _quiet,
    _small,
    _source,
)


@dataclass
class Plan:
    """Ровно то, что правило у плана и спрашивает."""

    ranked: list[Release] = field(default_factory=list)
    picture: Picture = field(default_factory=lambda: Picture(title="Кино", year=1999))
    want: Episode | None = None
    runtime: float = RUNTIME
    warn_mbit: float = 20.0
    hard_mbit: float = 0.0
    copy_hevc: bool = False
    last_resort: bool = False


def test_the_missing_episode_is_judged_before_everything_else() -> None:
    piece = rel(name="огрызок BDMV", kind="tv", seasons=(1,), episodes=(1,))
    assert drop_reason(piece, Plan(want=Episode(1, 5))) == phrase("rank.reason_no_episode")


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


def test_a_release_of_another_picture_is_named_so_and_not_by_the_gates() -> None:
    """Раздача с годным кодеком и кадром, выкинутая очередью как чужая, - не «кодек не тот».

    «It Follows» 2014 в пуле «Оно» 2017: ворота её пустили бы, выкинул год.
    """
    it = Picture(title="Оно", year=2017)
    follows = rel(name="Оно приходит за тобой / It Follows (2014) BDRip 1080p")
    object.__setattr__(follows, "year", 2014)
    assert drop_reason(follows, Plan(picture=it)) == phrase("rank.reason_other_year")
    naruto = Picture(title="Наруто", year=2002, kind="tv", original="Naruto")
    shippuuden = rel(name="Наруто [ТВ-2]", kind="tv", seasons=(1,))
    object.__setattr__(shippuuden, "original", "Naruto: Shippuuden")
    assert drop_reason(shippuuden, Plan(picture=naruto, want=Episode(1, 1))) == phrase(
        "rank.reason_other_work"
    )
    sac = Picture(title="Синдром одиночки", year=2002, kind="tv")
    gig = rel(name="Синдром одиночки (ТВ-2) / 2nd GIG [26 из 26] [2004]", kind="tv")
    object.__setattr__(gig, "year", 2004)
    assert drop_reason(gig, Plan(picture=sac, want=Episode(1, 1))) == phrase(
        "rank.reason_later_form"
    )
