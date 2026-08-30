"""Проверяет выражения, которыми справка читает статью Википедии."""

from tests.articles import CARS, HP_FRANCHISE, NOT_CINEMA
from torrcast.domain.facts import patterns


def test_the_cinema_word_is_caught_whole_and_not_as_a_substring() -> None:
    """Косвенный падеж - упоминание кино, а сама статья про человека."""
    assert patterns._CINEMA_RE.search(CARS)
    assert not patterns._CINEMA_RE.search(NOT_CINEMA["Уотсон, Эмма"])
    assert patterns._CINEMA_RE.search(HP_FRANCHISE), "«серия фильмов» - вписанный оборот"


def test_the_year_is_taken_only_from_the_words_that_name_a_year() -> None:
    """«1917» первым в тексте стоит названием, а не годом выпуска."""
    assert patterns._YEAR_RE.search("фильм 2006 года")
    assert not patterns._YEAR_RE.search("«1917» — военный фильм")


def test_the_disambiguation_bracket_is_cut_only_from_the_tail() -> None:
    """«Восхождение (фильм, 1976)» → «Восхождение»; скобка в середине имени остаётся."""
    assert patterns._TAIL_RE.sub("", "Восхождение (фильм, 1976)") == "Восхождение"
    assert patterns._TAIL_RE.sub("", "Ванда/Вижн") == "Ванда/Вижн"


def test_hieroglyphs_and_cyrillic_are_told_apart_from_latin() -> None:
    """Скобка японского кино двуязычна, и латиница в ней - ещё не название."""
    assert patterns._CJK.search("進撃の巨人")
    assert patterns._CYRILLIC.search("Тачки")
    assert not patterns._CYRILLIC.search("Cars")


def test_the_pointer_line_is_cut_whole() -> None:
    """Указатель кончается точкой с пробелом, а за ним стоит настоящая первая фраза."""
    cut = patterns._HATNOTE_RE.sub("", "О сериале см. статью 7 самураев. «Семь самураев» — драма.")
    assert cut.startswith("«Семь самураев»")


def test_the_pointer_forms_without_the_word_see_are_known_by_their_formula() -> None:
    """Формы, снятые с живых статей: слова «см.» в них нет, границей служит перенос строки.

    Каждая строка тут доехала до выдачи ``extract`` настоящей Википедии; шаблонные шляпки
    она вырезает сама, а эти дописаны в статьях руками (TC-908).
    """
    forms = (
        "Не путать с Звёздные войны: Войны клонов (мультсериал, 2003)",
        "Не путать со станцией Салка Свердловской железной дороги.",
        "Не следует путать с Списки округов США",
        "Запрос «Боксёрша» перенаправляется сюда.",
        "В Википедии есть статьи о других людях с именем Умберто.",
        "У этого термина существуют и другие значения, см. Мильна",
        "Эта статья — о клубе, существовавшем в 1925—2016 годах",
    )
    for form in forms:
        cut = patterns._HATNOTE_LINE_RE.sub("", f"{form}\n«Картина» — фильм 2008 года.")
        assert cut.startswith("«Картина»"), form


def test_a_first_paragraph_without_the_formula_stays_the_text_of_the_article() -> None:
    """Абзац режется по формуле, а не по тому, что он первый: иначе пропало бы описание."""
    own = "«О́ко» (англ. The Eye) — фильм ужасов 2008 года.\n\nСнят братьями Пан."
    assert patterns._HATNOTE_LINE_RE.sub("", own) == own
    assert patterns._HATNOTE_LINE_RE.sub("", "Не так давно вышел фильм.\nВторой абзац.") == (
        "Не так давно вышел фильм.\nВторой абзац."
    )
