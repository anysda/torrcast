"""Картины карты с голосами: :meth:`ImdbNames.pictures`, мерка известности тёзок."""

from pathlib import Path

from tests.articles import RU_MAP
from tests.fakes.rating_dump import FakeRatingDump
from tests.fakes.text_source import FakeTextSource
from torrcast.adapters.wiki.imdb_names import ImdbNames
from torrcast.domain.facts.map_picture import MapPicture


def _names(tmp_path: Path, votes: dict[str, int]) -> ImdbNames:
    path = tmp_path / "imdb-ru-names.tsv"
    return ImdbNames(FakeTextSource({path: RU_MAP}), FakeRatingDump(counted=votes), path)


def test_every_namesake_comes_with_its_kind_year_and_votes(tmp_path: Path) -> None:
    """Фильм и сериал одного имени приходят оба, с голосами по своему ``tconst``."""
    names = _names(tmp_path, {"tt1111111": 51000})

    assert names.pictures("пятая  ВЛАСТЬ") == [
        MapPicture("Пятая власть", 2013, False, "The Fifth Estate", 51000),
        MapPicture("Пятая власть", 2001, True, "Fifth Power", 0),
    ]


def test_a_name_the_map_does_not_know_has_no_pictures(tmp_path: Path) -> None:
    assert _names(tmp_path, {}).pictures("Властелин") == []
