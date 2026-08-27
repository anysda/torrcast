"""Проверяет офлайн-карту русских прокатных имён IMDb - последний шаг справки."""

from pathlib import Path

from tests.articles import RU_MAP
from tests.fakes.rating_dump import FakeRatingDump
from tests.fakes.text_source import FakeTextSource
from torrcast.adapters.wiki.imdb_names import ImdbNames


def _names(tmp_path: Path, rows: str = RU_MAP, votes: dict[str, int] | None = None) -> ImdbNames:
    path = tmp_path / "imdb-ru-names.tsv"
    return ImdbNames(FakeTextSource({path: rows}), FakeRatingDump(counted=votes or {}), path)


def test_a_picture_without_an_article_gets_its_original_from_the_offline_map(
    tmp_path: Path,
) -> None:
    """Статьи нет, а прокатное имя есть: карта отдаёт оригинал и год, и это не догадка."""
    found = _names(tmp_path).look("Американская фабрика", False)

    assert found.title == "American Factory"
    assert found.year == 2019
    assert not found.guessed


def test_the_map_matches_despite_case_and_punctuation(tmp_path: Path) -> None:
    """Регистр и разделители имя не меняют: ключ карты нормализован с обеих сторон."""
    assert _names(tmp_path).look("американская  ФАБРИКА!", False).title == "American Factory"


def test_the_map_is_parsed_once_per_process(tmp_path: Path) -> None:
    """Файл - сотни тысяч строк: второй раз его никто не разбирает."""
    catalogue = _names(tmp_path)
    source = catalogue.source
    assert isinstance(source, FakeTextSource)

    catalogue.look("Американская фабрика", False)
    catalogue.look("Пятая власть", False)

    assert len(source.reads) == 1


def test_an_exact_name_year_and_type_give_the_rating_id_without_a_full_index(
    tmp_path: Path,
) -> None:
    """Меню читает несколько точных строк, не строя паспортный индекс всей карты."""
    catalogue = _names(tmp_path)

    found = catalogue.ids([("Американская фабрика", 2019, "movie")])

    assert found == {("Американская фабрика", 2019): "tt9351980"}
    source = catalogue.source
    assert isinstance(source, FakeTextSource)
    assert len(source.reads) == 1


def test_a_missing_map_file_is_silence_not_a_crash(tmp_path: Path) -> None:
    """Нет файла карты (установка без справки) - паспорт пуст, и это не сбой."""
    path = tmp_path / "no-such-file.tsv"
    catalogue = ImdbNames(FakeTextSource(), FakeRatingDump(), path)

    assert not catalogue.look("Американская фабрика", False)


def test_the_votes_break_the_tie_between_namesakes(tmp_path: Path) -> None:
    """Два фильма под одним именем: выбирает число голосов, и без них карта молчит."""
    votes = {"tt3333333": 120, "tt4444444": 68000}

    assert _names(tmp_path, votes=votes).look("Совпадение", False).title == "Mere Coincidence"
    assert not _names(tmp_path).look("Совпадение", False)
