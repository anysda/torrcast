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


def test_the_rating_ids_do_not_reread_the_map_for_every_menu(tmp_path: Path) -> None:
    """🔴 Каждый добор справки и каждая пачка обложек читали и сводили файл заново."""
    catalogue = _names(tmp_path)

    catalogue.ids([("Американская фабрика", 2019, "movie")])
    again = catalogue.ids([("американская  ФАБРИКА!", 2019, "movie"), ("Нет такой", 1999, "tv")])

    assert again == {("американская  ФАБРИКА!", 2019): "tt9351980"}
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


def test_an_original_name_gets_its_russian_release_names_of_the_same_year_and_type(
    tmp_path: Path,
) -> None:
    """Латинская плитка находит прокатное имя по оригиналу; чужие год и тип не подходят."""
    rows = (
        "Аватар\ttt0499549\tmovie\tAvatar\t2009\n"
        "Аватар\ttt27931855\ttvSeries\tAvatar\t2022\n"
        "Аватар 3D\ttt0499549\tmovie\tAvatar\t2009\n"
        "Кибервойны\ttt0270841\tmovie\tCyber Wars\t2009\n"
    )
    catalogue = _names(tmp_path, rows)

    found = catalogue.ru_names([("avatar", 2009, "movie"), ("Avatar", 2022, "movie")])

    assert found == {("avatar", 2009): ["Аватар", "Аватар 3D"]}


def test_an_original_name_gives_the_imdb_id_of_the_same_year_and_type(tmp_path: Path) -> None:
    """Под оригиналом «Lioness» 2023 карта держит сериал tt13111078; фильм того же имени - нет."""
    rows = (
        "Спецназ: Львица\ttt13111078\ttvSeries\tLioness\t2023\n"
        "Львица\ttt13111078\ttvSeries\tLioness\t2023\n"
        "Львица\ttt7777777\tmovie\tLioness\t2023\n"
    )

    found = _names(tmp_path, rows).original_ids([("Lioness", 2023, "tv")])

    assert found == {("Lioness", 2023): ["tt13111078"]}


SERIES_MAP = (
    "Интерны\ttt1647423\ttvSeries\tInterny\t2010\n"
    "Ван-Пис\ttt0388629\ttvSeries\tOne Piece\t1999\n"
    "Ван-Пис\ttt11737520\ttvSeries\tOne Piece\t2023\n"
    "Ван-Пис\ttt0000009\tmovie\tOne Piece\t2000\n"
    "Укрытие\ttt0000010\tmovie\tShelter\t2023\n"
    "Бункер\ttt14688458\ttvSeries\tSilo\t2023\n"
)


def test_a_series_id_is_the_one_series_of_the_name_and_the_nearest_year(tmp_path: Path) -> None:
    catalogue = _names(tmp_path, SERIES_MAP)

    assert catalogue.series_id("Интерны", "", 2011) == "tt1647423", "год раздачи соседний"
    assert catalogue.series_id("Ван-Пис", "One Piece", 2023) == "tt11737520"
    assert catalogue.series_id("Ван-Пис", "", None) == "", "два сериала без года"
    assert catalogue.series_id("Укрытие", "Silo", 2023) == "tt14688458", "по оригиналу"
    assert catalogue.series_id("Интерны 11", "", 2014) == ""
