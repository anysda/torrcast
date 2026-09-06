"""Проверяет picture_tile: плитка полки из картины, метка качества - максимум по раздачам."""

from __future__ import annotations

from torrcast.domain.picture import Picture
from torrcast.domain.picture_tile import picture_tile
from torrcast.domain.release import Release


def _release(quality: str | None, seeders: int = 1) -> Release:
    return Release(
        raw_name=f"Раздача {quality}", title="Матрица", size=1, seeders=seeders, quality=quality
    )


def test_the_tile_carries_the_contract_fields_and_the_original_for_lookup() -> None:
    """Плитка несёт ключ, имя, год, род, метку качества, запрос и оригинал для розыска."""
    picture = Picture("Матрица", 1999, "movie", original="The Matrix", releases=[_release("1080p")])

    tile = picture_tile(picture)

    assert tile == {
        "key": picture.key,
        "title": "Матрица",
        "year": 1999,
        "kind": "movie",
        "quality": "1080p",
        "query": "Матрица",
        "original": "The Matrix",
    }


def test_the_quality_label_is_the_best_across_releases() -> None:
    """Раздач несколько - метка берётся у той, чья высота больше, а не у первой попавшейся."""
    picture = Picture(
        "Матрица", 1999, releases=[_release("480p"), _release("2160p"), _release("720p")]
    )

    assert picture_tile(picture)["quality"] == "2160p"


def test_no_release_names_a_quality_gives_none() -> None:
    """Ни одна раздача не назвала качество - метка ``None``, а не выдуманная строка."""
    picture = Picture("Матрица", 1999, releases=[_release(None)])

    assert picture_tile(picture)["quality"] is None
