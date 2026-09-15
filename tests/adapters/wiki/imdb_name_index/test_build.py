"""Сборка дискового индекса карты русских прокатных имён IMDb."""

from pathlib import Path

from tests.articles import RU_MAP
from tests.fakes.rating_dump import FakeRatingDump
from tests.fakes.text_source import FakeTextSource
from torrcast.adapters.wiki.imdb_name_index.build import build
from torrcast.adapters.wiki.imdb_name_index.rows import rows
from torrcast.adapters.wiki.imdb_names import ImdbNames
from torrcast.domain.facts.map_picture import MapPicture


def test_a_ready_index_reads_only_the_requested_name(tmp_path: Path) -> None:
    """🔴 Карта в RAM стоила каждому новому процессу 2.3 с и 90 МБ."""
    path = tmp_path / "imdb-ru-names.tsv"
    path.write_text(RU_MAP, encoding="utf-8")
    source = FakeTextSource()
    names = ImdbNames(source, FakeRatingDump(counted={"tt1111111": 51000}), path)

    assert build(path) is True
    assert names.pictures("пятая  ВЛАСТЬ") == [
        MapPicture("Пятая власть", 2013, False, "The Fifth Estate", 51000),
        MapPicture("Пятая власть", 2001, True, "Fifth Power", 0),
    ]
    assert source.reads == [], "готовый индекс не читает TSV в процессе поиска"


def test_an_unchanged_dump_does_not_rebuild_its_index(tmp_path: Path) -> None:
    """Индекс собирается при обновлении выгрузки, а не при каждом запуске установщика."""
    path = tmp_path / "imdb-ru-names.tsv"
    path.write_text(RU_MAP, encoding="utf-8")

    assert build(path) is True
    assert build(path) is False


def test_a_changed_dump_rebuilds_its_index(tmp_path: Path) -> None:
    path = tmp_path / "imdb-ru-names.tsv"
    path.write_text(RU_MAP, encoding="utf-8")
    assert build(path) is True

    path.write_text(RU_MAP + "Тачки\ttt0317219\tmovie\tCars\t2006\n", encoding="utf-8")

    assert build(path) is True
    assert rows(path.with_suffix(".sqlite3"), "Тачки") == [
        ("tt0317219", "movie", "Cars", "2006", "Тачки")
    ]


def test_the_index_answers_as_the_dump_itself(tmp_path: Path) -> None:
    """Индекс - другой способ читать ту же выгрузку, включая починку латинских омоглифов."""
    dump = RU_MAP + "Тaчки\ttt0317219\tmovie\tCars\t2006\n"
    path = tmp_path / "imdb-ru-names.tsv"
    path.write_text(dump, encoding="utf-8")
    votes = FakeRatingDump(counted={"tt1111111": 51000, "tt4444444": 68000})
    asked = ["Тачки", "Пятая власть", "Совпадение", "Колыма - родина нашего страха"]
    from_dump = ImdbNames(FakeTextSource(files={path: dump}), votes, path)
    expected = {title: from_dump.pictures(title) for title in asked}

    assert build(path) is True
    from_index = ImdbNames(FakeTextSource(), votes, path)
    assert {title: from_index.pictures(title) for title in asked} == expected
    assert all(expected.values())
