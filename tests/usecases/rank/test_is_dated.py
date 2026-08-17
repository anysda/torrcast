"""Раздача пахнет старьём - до всякого ffprobe, по имени и размеру."""

from __future__ import annotations

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.usecases.rank.is_dated import is_dated


def test_a_name_that_admits_its_age_is_dated() -> None:
    old = rel(name="Кино (1999) DVDRip", source="DVDRip", codec=None, quality=None)
    assert is_dated(old, RUNTIME)
    assert is_dated(rel(name="Кино (1999) Moana.2.avi"), RUNTIME)


def test_a_name_below_hd_is_dated_and_an_hd_one_is_not() -> None:
    assert is_dated(rel(quality="480p"), RUNTIME)
    assert not is_dated(rel(quality="720p"), RUNTIME)


def test_a_silent_name_with_a_thin_weight_is_dated() -> None:
    """«Моана 2»: 1.46 ГБ, 221 сид, ни одного маркера в имени, а внутри .avi."""
    thin = rel(
        name="Моана 2 (2024) WEB-DL] Dub (MovieDalen)",
        title="Моана 2",
        quality=None,
        source="WEB-DL",
        size_gb=1.46,
    )
    assert is_dated(thin, RUNTIME)
    assert not is_dated(rel(quality=None, source="WEB-DL", size_gb=8), RUNTIME)


def test_a_season_pack_that_counts_no_episodes_is_judged_by_the_ceiling() -> None:
    """🟡 «Чёрные паруса» с одним сидом вставали выше живого сериала на 61 сид."""
    pack = rel(
        name="Чёрные паруса [S01-04] HDTV",
        title="Чёрные паруса",
        quality=None,
        codec=None,
        source=None,
        kind="tv",
        seasons=(1, 2, 3, 4),
        size_gb=10.24,
    )
    assert is_dated(pack, RUNTIME)
