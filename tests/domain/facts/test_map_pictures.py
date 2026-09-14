"""Зеркало :mod:`torrcast.domain.facts.map_pictures`: строки карты, сведённые с голосами."""

from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.map_pictures import map_pictures


def test_rows_keep_their_kind_year_and_votes() -> None:
    """Сериал и фильм не смешиваются, голоса берутся по ``tconst``, неизвестному - ноль."""
    rows = [
        ("tt6857112", "movie", "Us", "2019", "Мы"),
        ("tt0000001", "tvSeries", "Us", "2020", "Мы"),
        ("tt0000002", "movie", "Мы", "\\N", "Мы"),
    ]

    pictures = map_pictures(rows, {"tt6857112": 399488})

    assert pictures == [
        MapPicture("Мы", 2019, False, "Us", 399488),
        MapPicture("Мы", 2020, True, "Us", 0),
        MapPicture("Мы", None, False, "Мы", 0),
    ]
