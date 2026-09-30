"""Зеркало :func:`foreign_reason`: почему раздача не наша - и в каком порядке это судится."""

from __future__ import annotations

from dataclasses import replace

from tests.usecases.rank.releases import rel
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.usecases.rank.foreign_reason import foreign_reason
from torrcast.usecases.rank.off_season import _no_episode

_NARUTO = Picture(title="Наруто", year=2002, kind="tv", original="Naruto")


def test_a_film_of_another_year_is_another_picture() -> None:
    it = Picture(title="Оно", year=2017)
    follows = replace(rel(name="It Follows (2014) BDRip 1080p"), year=2014)

    assert foreign_reason(follows, it, None) == phrase("rank.reason_other_year")
    assert foreign_reason(replace(follows, year=2017), it, None) == ""


def test_a_missing_episode_is_judged_before_another_work() -> None:
    """Порядок тот же, что у очереди: огрызок чужой работы называется огрызком."""
    shippuuden = replace(
        rel(name="Наруто [ТВ-2]", kind="tv", seasons=(1,), episodes=(1,)),
        original="Naruto: Shippuuden",
    )

    assert foreign_reason(shippuuden, _NARUTO, Episode(1, 5)) == _no_episode()
    assert foreign_reason(shippuuden, _NARUTO, Episode(1, 1)) == phrase("rank.reason_other_work")


def test_a_later_form_is_named_as_its_own_reason() -> None:
    sac = Picture(title="Синдром одиночки", year=2002, kind="tv")
    gig = replace(rel(name="Синдром одиночки (ТВ-2) / 2nd GIG [2004]", kind="tv"), year=2004)

    assert foreign_reason(gig, sac, Episode(1, 1)) == phrase("rank.reason_later_form")


def test_a_film_has_no_series_reasons() -> None:
    """Без нужной серии (фильм) ни другая работа, ни поздняя форма не судятся."""
    shippuuden = replace(rel(name="Наруто [ТВ-2]", kind="tv"), original="Naruto: Shippuuden")

    assert foreign_reason(shippuuden, _NARUTO, None) == ""
