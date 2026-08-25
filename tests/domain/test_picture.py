"""Зеркало :mod:`torrcast.domain.picture`: картина и то, что она знает о себе."""

from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _release(seeders: int = 0, copies: int = 1, collection: bool = False) -> Release:
    return Release(
        raw_name="Брат 1997", title="Брат", seeders=seeders, copies=copies, collection=collection
    )


def test_the_key_names_the_kind_the_name_and_the_year() -> None:
    """Ключом картина узнаётся между прогонами, и год в нём стоит не для красоты."""
    assert Picture(title="Брат", year=1997).key == "movie:брат:1997"
    assert Picture(title="Брат", year=1997, kind="tv").key == "tv:брат:1997"


def test_a_picture_without_a_year_is_told_apart_by_its_original_name() -> None:
    """Год неизвестен - ключом остаётся пара имён, иначе тёзки слились бы в одну."""
    assert Picture(title="Брат", year=None, original="Brother").key == "movie:брат-brother:0"


def test_the_rows_count_every_copy_and_not_every_release() -> None:
    """Одна раздача бывает выдана несколькими трекерами: строк столько, сколько копий."""
    picture = Picture(title="Брат", year=1997, releases=[_release(copies=3), _release(copies=2)])

    assert picture.rows == 5


def test_the_seeders_of_the_picture_are_those_of_its_liveliest_release() -> None:
    picture = Picture(title="Брат", year=1997, releases=[_release(seeders=2), _release(seeders=9)])

    assert picture.seeders == 9
    assert Picture(title="Брат", year=1997).seeders == 0


def test_a_picture_is_a_collection_only_when_every_release_is_one() -> None:
    """Хотя бы одна одиночная раздача - и картину можно показать саму по себе."""
    whole = Picture(title="Брат", year=1997, releases=[_release(collection=True)])
    mixed = Picture(title="Брат", year=1997, releases=[_release(collection=True), _release()])

    assert whole.collection
    assert not mixed.collection
    assert not Picture(title="Брат", year=1997).collection
