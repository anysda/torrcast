"""Зеркало :mod:`torrcast.domain.facts.proof_in_map`: чем карта доказывает картину выдачи."""

from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.proof_in_map import _renown, proof_in_map
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify

_MAP = {
    "мы": [
        MapPicture("Мы", 2019, False, "Us", 399488),
        MapPicture("Мы", 2018, False, "Wij", 4311),
        MapPicture("Мы", 2020, True, "Us", 3383),
    ],
    "фарго": [
        MapPicture("Фарго", 1996, False, "Fargo", 795799),
        MapPicture("Фарго", 2014, True, "Fargo", 474650),
    ],
}


def _known(title: str) -> list[MapPicture]:
    return _MAP.get(slugify(title), [])


def test_the_exact_name_type_and_year_prove_the_picture() -> None:
    """🔴 «Мы» (2019) в выдаче - это Us: тройка сошлась, голландская тёзка 2018-го слабее."""
    proof = proof_in_map(Picture(title="Мы", year=2019), _known)

    assert proof is not None
    assert (proof.original, proof.votes) == ("Us", 399488)


def test_a_film_and_a_series_of_one_name_do_not_prove_each_other() -> None:
    """«Фарго» сериал 2014-го карта доказывает сериалом, а не фильмом 1996-го."""
    series = proof_in_map(Picture(title="Фарго", year=2015, kind="tv"), _known)
    film = proof_in_map(Picture(title="Фарго", year=2014), _known)

    assert series is not None
    assert (series.year, series.series) == (2014, True)
    assert film is None


def test_a_series_is_proven_by_a_start_before_its_season() -> None:
    """Сезон 2023 года у сериала, начатого в 2014-м, - та же картина."""
    assert proof_in_map(Picture(title="Фарго", year=2023, kind="tv"), _known) is not None
    assert proof_in_map(Picture(title="Фарго", year=2013, kind="tv"), _known) is None


def test_a_picture_without_a_year_or_of_another_kind_is_not_proven() -> None:
    """Имя одно на десяток тёзок: без года отличить их нечем."""
    assert proof_in_map(Picture(title="Мы", year=None), _known) is None
    assert proof_in_map(Picture(title="Мы", year=2019, kind="other"), _known) is None
    assert proof_in_map(Picture(title="Мы", year=2005), _known) is None


def test_renown_is_zero_when_the_map_is_silent() -> None:
    assert _renown([Picture(title="Властелин", year=1999)], _known) == 0
    assert _renown([Picture(title="Мы", year=2019)], _known) == 399488
