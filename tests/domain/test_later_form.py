"""Зеркало :func:`torrcast.domain.later_form.later_form`."""

from __future__ import annotations

import pytest

from torrcast.domain.episode import Episode
from torrcast.domain.later_form import later_form
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release

GIG = (
    "Призрак в доспехах: Синдром одиночки (ТВ-2) / Koukaku Kidoutai S.A.C. 2nd GIG (Камияма"
    " Кэндзи) [TV+Special] [26+26 из 26+26] [RUS(ext),JAP+Sub] [2004, меха, BDRip] [1080p]"
)
_SAC = Picture(title="Призрак в доспехах: Синдром одиночки", year=2002, kind="tv")


def _release(name: str, year: int | None = 2004) -> Release:
    return Release(raw_name=name, title="x", year=year, kind="tv")


def test_the_second_form_of_another_year_has_no_first_season() -> None:
    """🔴 «Синдром одиночки» s1e1 играл первую серию 2nd GIG: «(ТВ-2)» лежала в пуле ТВ-1."""
    assert later_form(_release(GIG), _SAC, Episode(1, 1))


@pytest.mark.parametrize(
    ("name", "year", "want"),
    [
        (GIG.replace("(ТВ-2)", "(ТВ-1)"), 2002, Episode(1, 1)),
        (GIG, 2002, Episode(1, 1)),  # картина сама и есть вторая форма
        (GIG, None, Episode(1, 1)),
        (GIG, 2004, Episode(2, 1)),
        ("Сериал / Show [S01] (2004) WEB-DL 1080p | Dub (ТВ-3) + DVO", 2004, Episode(1, 1)),
        ("Сериал / Show [S01] (2004) WEB-DL 1080p | MVO (TV-2)", 2004, Episode(1, 1)),
    ],
)
def test_the_first_form_its_own_year_and_a_tv_channel_keep_the_release(
    name: str, year: int | None, want: Episode
) -> None:
    """TC-985: «Dub (ТВ-3)» - телеканал озвучки, а не третья форма."""
    assert not later_form(_release(name, year), _SAC, want)
