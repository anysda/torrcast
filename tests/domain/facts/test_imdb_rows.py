"""Проверяет разбор выгрузок IMDb: оценки, голоса и карта прокатных имён."""

from tests.articles import RATINGS_DUMP, RU_MAP
from torrcast.domain.facts.imdb_rows import (
    _named_origin,
    _picture_ids_from_lines,
    _repair_ru_name,
    _ru_rows,
    _scores,
    _vote_counts,
)
from torrcast.domain.facts.settings import SOURCE_MAP
from torrcast.domain.slugify import slugify


def _rows() -> dict[str, list[tuple[str, str, str, str, str]]]:
    return _ru_rows(RU_MAP.splitlines(keepends=True))


def test_the_ratings_dump_gives_scores_and_votes_without_its_header() -> None:
    """Шапка «tconst averageRating numVotes» - не картина, и в словарь не попадает."""
    lines = RATINGS_DUMP.splitlines(keepends=True)
    assert _scores(lines) == {"tt0317219": "7.3", "tt4444444": "7.4"}
    assert _vote_counts(lines) == {"tt0317219": 544373, "tt4444444": 68000}
    assert _scores([]) == {} and _vote_counts([]) == {}


def test_the_map_key_is_the_normalized_name() -> None:
    """Регистр и разделители имя не меняют: ключ карты нормализован с обеих сторон."""
    rows = _rows()
    assert rows[slugify("американская  ФАБРИКА!")][0][2] == "American Factory"


def test_the_map_repairs_latin_homoglyphs_inside_a_russian_name() -> None:
    """Латинские ``B`` и ``y`` из выгрузки не делают русское прокатное имя мёртвым."""
    assert _repair_ru_name("B двyх шагах от славы") == "В двух шагах от славы"


def test_the_map_keeps_intentional_mixed_script_names() -> None:
    """Брендовая игра алфавитами - не опечатка, если буквы не одни омоглифы."""
    assert _repair_ru_name("SuperПерцы") == "SuperПерцы"


def test_a_picture_without_an_article_gets_its_original_from_the_offline_map() -> None:
    """Статьи нет, а прокатное имя есть: карта отдаёт оригинал и год, и это не догадка."""
    found = _named_origin(_rows()[slugify("Американская фабрика")], False, dict)
    assert found.title == "American Factory"
    assert found.year == 2019
    assert found.name == "Американская фабрика"
    assert found.source == SOURCE_MAP
    assert not found.guessed, "пара «имя - картина» из выгрузки - утверждение каталога"


def test_the_map_honors_the_spelled_out_type() -> None:
    """Фильм и сериал под одним русским именем разводятся подсказанным типом."""
    candidates = _rows()[slugify("Пятая власть")]
    movie = _named_origin(candidates, False, dict)
    series = _named_origin(candidates, True, dict)
    assert (movie.title, movie.year) == ("The Fifth Estate", 2013)
    assert (series.title, series.year) == ("Fifth Power", 2001)


def test_several_namesakes_are_a_guess_chosen_by_the_crowd() -> None:
    """Два фильма под одним именем - выбирает число голосов, и паспорт помечен догадкой."""
    votes = {"tt3333333": 120, "tt4444444": 68000}
    found = _named_origin(_rows()[slugify("Совпадение")], False, lambda: votes)
    assert found.title == "Mere Coincidence"
    assert found.guessed, "выбор по голосам - чья-то оценка, а не утверждение каталога"


def test_namesakes_without_votes_stay_silent() -> None:
    """Однофамильцы есть, а голосов нет - неподтверждённый выбор хуже пустого паспорта."""
    assert not _named_origin(_rows()[slugify("Совпадение")], False, dict)


def test_a_single_candidate_never_asks_for_the_votes() -> None:
    """Голоса стоят чтения файла: за ними идут только там, где есть из чего выбирать."""
    asked: list[str] = []

    def votes() -> dict[str, int]:
        asked.append("votes")
        return {}

    assert _named_origin(_rows()[slugify("Американская фабрика")], False, votes)
    assert asked == []


def test_a_russian_original_is_a_year_not_a_latin_name() -> None:
    """У русской картины нет латинского имени: карта отдаёт год, а ``title`` пуст."""
    found = _named_origin(_rows()[slugify("Колыма - родина нашего страха")], False, dict)
    assert found.title == "", "кириллический оригинал - не имя для добора латиницей"
    assert found.year == 2019
    assert found.name == "Колыма - родина нашего страха"


def test_a_name_nobody_catalogued_is_silence() -> None:
    """Чего в карте нет - о том молчим, и это не сбой."""
    assert not _named_origin([], False, dict)


PARASITES = [
    "Паразиты\ttt0210945\tmovie\tLes parasites\t1999\n",
    "Паразиты\ttt0398606\tmovie\tParasites\t2004\n",
    "Паразиты\ttt6751668\tmovie\tGisaengchung\t2016\n",
    "Матрица\ttt0133093\tmovie\tThe Matrix\t1999\n",
]


def test_several_namesakes_asked_in_one_call_all_get_their_own_id() -> None:
    """🔴 Тёзки разных лет спрашиваются вместе: имя - не ключ, ответ нужен каждой."""
    asked: list[tuple[str, int | None, str]] = [
        ("Паразиты", 1999, "movie"),
        ("Паразиты", 2004, "movie"),
        ("Паразиты", 2016, "movie"),
    ]
    found = _picture_ids_from_lines(PARASITES, asked)
    assert found == {
        ("Паразиты", 1999): "tt0210945",
        ("Паразиты", 2004): "tt0398606",
        ("Паразиты", 2016): "tt6751668",
    }


def test_the_name_is_compared_by_the_same_rule_as_the_rest_of_the_map() -> None:
    """🔴 Кавычки и точка - не другое имя: сравнение идёт сведённым именем."""
    lines = ["Рерберг и Тарковский. Обратная сторона «Сталкера»\ttt1373300\tmovie\t\t2009\n"]
    asked: list[tuple[str, int | None, str]] = [
        ('Рерберг и Тарковский: Обратная сторона "Сталкера"', 2009, "movie")
    ]
    found = _picture_ids_from_lines(lines, asked)
    assert found == {('Рерберг и Тарковский: Обратная сторона "Сталкера"', 2009): "tt1373300"}


def test_two_ids_on_one_name_and_year_stay_silent() -> None:
    """Из двух одногодок карта не выбирает: чужая картинка хуже отсутствующей."""
    lines = [
        "Брат\ttt35064377\tmovie\tBrat\t2025\n",
        "Брат\ttt29930430\tmovie\tBrat\t2025\n",
    ]
    assert _picture_ids_from_lines(lines, [("Брат", 2025, "movie")]) == {}


def test_the_kind_still_parts_a_series_from_a_film() -> None:
    """Сериал под именем фильма - не та картина, и год тут не помощник."""
    lines = ["Паразиты\ttt10800134\ttvSeries\tParasyte\t2019\n"]
    assert _picture_ids_from_lines(lines, [("Паразиты", 2019, "movie")]) == {}
    assert _picture_ids_from_lines(lines, [("Паразиты", 2019, "tv")]) == {
        ("Паразиты", 2019): "tt10800134"
    }


def test_a_picture_without_a_year_is_not_asked_of_the_map() -> None:
    """Без года сверять нечем: неподтверждённое совпадение имени - не ответ."""
    assert _picture_ids_from_lines(PARASITES, [("Паразиты", None, "movie")]) == {}
