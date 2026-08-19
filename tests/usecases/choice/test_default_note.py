"""Зеркало :mod:`torrcast.usecases.choice.default_note`: одна честная строка про подмену.

🔴 TC-198. Молчаливая подмена КАРТИНЫ - худший вид брака, а дефолт франшизы подменяет её
буднично: пропускает мёртвую первую часть, уходит с однораздачной, считается среди
сериалов - и всё это без единого слова. В замере каталога так молча прошли десять
спорных запросов из четырнадцати.
"""

from __future__ import annotations

from tests.usecases.choice.world import film, parts, plan
from torrcast.usecases.choice.default_note import _passed_why, default_note

VHS = film("Moana 1926 DVDRip XviD", seeders=100, codec="XviD", quality=None)
SD = film("Кино 2020 WEB-DLRip 480p", seeders=100, quality="480p")


def test_a_swap_of_type_is_named_by_both_pictures_and_by_the_reason() -> None:
    """Спросили серию, а живее полнометражка - строка называет обе картины и причину."""
    wife = [
        plan("Хорошая жена", 1987, seeders=40, asked_series=True),
        plan("Хорошая жена", 2015, seeders=18, kind="tv", asked_series=True),
    ]

    said = default_note(wife, "хорошая жена s1e1")

    assert said == (
        "спросили «хорошая жена s1e1» - беру «Хорошая жена (2015, сериал)», "
        "а не «Хорошая жена (1987)»: спросили серию, а это другой тип"
    )


def test_a_skipped_earlier_part_is_named_together_with_the_reason_it_was_skipped() -> None:
    """Пропущенная часть названа поимённо: «беру Y, а не X, потому что Z».

    Без имени пропущенной картины строка сообщала бы человеку ровно то, что он и так
    видит на экране, - какую картину берут, - и молчала о том, чего он не видит.
    """
    moana = [
        plan("Моана: романтика золотого века", 1926, pool=[VHS]),
        plan("Моана", 2016, seeders=222),
    ]

    said = default_note(moana, "моана")

    assert said == (
        "спросили «моана» - беру «Моана (2016)», а не «Моана: романтика золотого века "
        "(1926)»: играть у неё нечем - ни одной годной раздачи"
    )


def test_without_the_words_of_the_person_the_line_keeps_everything_but_the_head() -> None:
    """``asked`` пуст - строка та же, только без головы «спросили X»."""
    moana = [plan("Моана: романтика золотого века", 1926, pool=[VHS]), plan("Моана", 2016)]

    assert default_note(moana).startswith("беру «Моана (2016)», а не ")


def test_a_namesake_by_year_is_said_out_loud_even_when_the_default_is_the_first_item() -> None:
    """Дефолт встал первым, но под тем же именем стоит другая картина - молчать нельзя.

    Человек, назвавший «мумия», получает «Мумию» - вопрос лишь, которую из трёх.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    said = default_note(mummy, "мумия")

    assert said == (
        "спросили «мумия» - беру «Мумия (1999)»: под этим именем есть ещё "
        "«Мумия (2017)» - другая картина"
    )


def test_taking_exactly_what_was_asked_for_is_not_a_swap_and_gets_no_line() -> None:
    """Взято ровно то, что назвали, - и говорить не о чем.

    Ровно это чинит TC-196: «голодные игры» → «Голодные игры» (2012) перестают быть
    сменой картины вообще, а строка там была бы шумом.
    """
    games = parts(("Голодные игры", 2012, 120), ("Голодные игры: И вспыхнет пламя", 2013, 90))

    assert default_note(games, "голодные игры") == ""


def test_each_of_the_four_reasons_says_a_different_thing_to_the_person() -> None:
    """🔴 Причины ровно четыре, и человеку они разные: одним словом их не заменить.

    Слепи их в одно «не подошла» - и человек не отличил бы каталог без нужной картины от
    мёртвого роя, а мёртвый рой от «есть только старьё».
    """
    nothing = [plan("Кино", 1999, pool=[VHS]), plan("Кино", 2001, seeders=90)]
    dead = parts(("Кино", 1999, 2), ("Кино", 2001, 90))
    junk = [plan("Кино", 1999, pool=[SD]), plan("Кино", 2001, seeders=90)]
    lonely = [
        plan("Кино", 1999, seeders=16),
        plan("Кино", 2001, pool=[film("a", seeders=28), film("b", seeders=20)]),
    ]

    assert _passed_why(nothing, 1, [1, 2]) == "играть у неё нечем - ни одной годной раздачи"
    assert _passed_why(dead, 1, [1, 2]) == "рой у неё мёртв - сидов 2"
    assert _passed_why(junk, 1, [1, 2]) == "живого HD у неё нет - одно старьё"
    # Счёт раздач - у ВЗЯТОЙ картины: у пропущенной он по построению ветки всегда один.
    assert _passed_why(lonely, 1, [1, 2]) == "у неё всего одна раздача, а тут их 2"


def test_the_torrent_count_is_taken_from_the_picture_the_default_took() -> None:
    """🔴 TC-681. «Тут их N» - это очередь ВЗЯТОЙ картины, а не пропущенной.

    Считалось у пропущенной же, и зритель читал самопротиворечивое «у неё всего одна
    раздача, а тут их 1» - по такой строке не понять, права ли машина.
    """
    falcon = [
        plan("Мальтийский сокол", 1931, seeders=16),
        plan(
            "Мальтийский сокол",
            1941,
            pool=[film("Сокол 1941 a", seeders=28), film("Сокол 1941 b", seeders=20)],
        ),
    ]

    assert default_note(falcon, "мальтийский сокол") == (
        "спросили «мальтийский сокол» - беру «Мальтийский сокол (1941)», а не "
        "«Мальтийский сокол (1931)»: у неё всего одна раздача, а тут их 2"
    )


def test_when_the_taken_picture_is_also_a_single_release_the_reason_is_not_printed() -> None:
    """У взятой тоже одна раздача - сравнение бессмысленно, и ветка молчит.

    Строка о подмене при этом остаётся: молчаливый перескок - худший вид брака, а
    врёт тут только хвост про раздачи, его и снимаем.
    """
    lonely = [
        plan("Кино", 1999, seeders=16),
        plan("Кино", 2001, seeders=90),
        plan("Кино", 2003, pool=[film("Кино 2003 a", seeders=50), film("Кино 2003 b", seeders=40)]),
    ]

    assert _passed_why(lonely, 1, [1, 2, 3]) == ""
    assert default_note(lonely, "кино") == (
        "спросили «кино» - беру «Кино (2001)», а не «Кино (1999)»"
    )
