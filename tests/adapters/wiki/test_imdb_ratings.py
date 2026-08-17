"""Проверяет чтение выгрузки оценок IMDb с диска."""

from pathlib import Path

from tests.fakes.text_source import FakeTextSource
from torrcast.adapters.wiki.imdb_ratings import ImdbRatings

DUMP = "tconst\taverageRating\tnumVotes\ntt0317219\t7.3\t544373\n"


def test_ratings_come_from_the_offline_dump(tmp_path: Path) -> None:
    """Оценка читается из выгрузки IMDb, а нет файла — просто нет оценок."""
    dump = tmp_path / "imdb-ratings.tsv"
    source = FakeTextSource({dump: DUMP})

    assert ImdbRatings(source, dump).scores() == {"tt0317219": "7.3"}
    assert ImdbRatings(source, tmp_path / "нет-такого").scores() == {}


def test_the_votes_are_parsed_once_per_process(tmp_path: Path) -> None:
    """Голоса спрашивают редко, но файл сотнями тысяч строк дважды не читают."""
    dump = tmp_path / "imdb-ratings.tsv"
    source = FakeTextSource({dump: DUMP})
    ratings = ImdbRatings(source, dump)

    assert ratings.votes() == {"tt0317219": 544373}
    assert ratings.votes() == {"tt0317219": 544373}
    assert source.reads == [dump], "второй раз выгрузка не разбирается"


def test_the_scores_are_read_afresh_every_time(tmp_path: Path) -> None:
    """Оценки читает один поход за справкой, и держать их между показами незачем."""
    dump = tmp_path / "imdb-ratings.tsv"
    source = FakeTextSource({dump: DUMP})
    ratings = ImdbRatings(source, dump)

    ratings.scores()
    ratings.scores()
    assert source.reads == [dump, dump]
