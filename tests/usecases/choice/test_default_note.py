"""Зеркало :mod:`torrcast.usecases.choice.default_note`: одна честная строка про подмену.

🔴 TC-198. Молчаливая подмена КАРТИНЫ - худший вид брака, а дефолт франшизы подменяет её
буднично: пропускает мёртвую первую часть, уходит с однораздачной, считается среди
сериалов - и всё это без единого слова. В замере каталога так молча прошли десять
спорных запросов из четырнадцати.
"""

from __future__ import annotations

from dataclasses import replace

from tests.usecases.choice.world import film, parts, plan
from torrcast.domain.catalogs.choice.en import en
from torrcast.domain.catalogs.phrase import phrase
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

    assert said == phrase(
        "choice.note_instead_asked_why",
        asked="хорошая жена s1e1",
        mine=f"Хорошая жена (2015{phrase('choice.series_mark')})",
        other="Хорошая жена (1987)",
        why=phrase("choice.why_other_kind"),
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
        phrase(
            "choice.note_instead_asked_why",
            asked="моана",
            mine="Моана (2016)",
            other="Моана: романтика золотого века (1926)",
            why=phrase("choice.why_nothing_playable"),
        )
    )


def test_without_the_words_of_the_person_the_line_keeps_everything_but_the_head() -> None:
    """``asked`` пуст - строка та же, только без головы «спросили X»."""
    moana = [plan("Моана: романтика золотого века", 1926, pool=[VHS]), plan("Моана", 2016)]

    assert default_note(moana) == phrase(
        "choice.note_instead_why",
        mine="Моана (2016)",
        other="Моана: романтика золотого века (1926)",
        why=phrase("choice.why_nothing_playable"),
    )


def test_a_namesake_by_year_is_said_out_loud_even_when_the_default_is_the_first_item() -> None:
    """Дефолт встал первым, но под тем же именем стоит другая картина - молчать нельзя.

    Человек, назвавший «мумия», получает «Мумию» - вопрос лишь, которую из трёх.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    said = default_note(mummy, "мумия")

    assert said == (
        phrase(
            "choice.note_namesake_asked",
            asked="мумия",
            mine="Мумия (1999)",
            others=phrase("choice.quoted", it="Мумия (2017)"),
        )
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

    assert _passed_why(nothing, 1, [1, 2]) == phrase("choice.why_nothing_playable")
    assert _passed_why(dead, 1, [1, 2]) == phrase("choice.why_dead_swarm", seeds=2)
    assert _passed_why(junk, 1, [1, 2]) == phrase("choice.why_no_hd")
    # Счёт раздач - у ВЗЯТОЙ картины: у пропущенной он по построению ветки всегда один.
    assert _passed_why(lonely, 1, [1, 2]) == phrase("choice.why_single_release", taken=2)


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

    assert default_note(falcon, "мальтийский сокол") == phrase(
        "choice.note_instead_asked_why",
        asked="мальтийский сокол",
        mine="Мальтийский сокол (1941)",
        other="Мальтийский сокол (1931)",
        why=phrase("choice.why_single_release", taken=2),
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
    assert default_note(lonely, "кино") == phrase(
        "choice.note_instead_asked", asked="кино", mine="Кино (2001)", other="Кино (1999)"
    )


def test_the_line_speaks_even_when_the_skipped_picture_was_no_candidate_at_all() -> None:
    """🔴 Строка молчит только там, где дефолт и есть первый пункт списка.

    Спросили серию, а первым пунктом стоит одноимённый фильм: кандидатом он не был
    никогда, и строка про смену типа о нём молчала - ей было нечего сравнивать. На
    экране же человек видел «Клинику» 1987 года первой строкой и жал Enter. Молчание
    строки обязано означать «смены не было», а не «я про это ничего не знаю».
    """
    clinic = [
        plan("Клиника", 1987, pool=[VHS], asked_series=True),
        plan("Клиника", 2001, seeders=105, kind="tv", asked_series=True),
    ]

    said = default_note(clinic, "клиника s7e1")

    assert said == (
        phrase(
            "choice.note_instead_asked_why",
            asked="клиника s7e1",
            mine=f"Клиника (2001{phrase('choice.series_mark')})",
            other="Клиника (1987)",
            why=phrase("choice.why_other_kind"),
        )
    )


def test_the_type_that_kept_the_default_in_place_is_named_too() -> None:
    """🔴 Дефолт остался первым пунктом ПОТОМУ, что спросили серию, - и это тоже решение.

    Живее тут одноимённая полнометражка, и без правила о типе Enter уехал бы на неё.
    Промолчи об этом - и вопроса о выборе не будет вовсе (:func:`certain_default`):
    молчание обеих строк читается как «другой картины, которую могли иметь в виду, нет».
    """
    ghoul = [
        plan("Токийский гуль", 2014, kind="tv", asked_series=True, pool=[SD]),
        plan("Токийский гуль", 2017, seeders=90, asked_series=True),
    ]

    said = default_note(ghoul, "токийский гуль s1e1")

    assert said == (
        phrase(
            "choice.note_instead_asked_why",
            asked="токийский гуль s1e1",
            mine=f"Токийский гуль (2014{phrase('choice.series_mark')})",
            other="Токийский гуль (2017)",
            why=phrase("choice.why_other_kind"),
        )
    )


def test_the_line_compares_against_the_default_no_narrowing_ever_touched() -> None:
    """🔴 TC-818. Сравнивать взятое строка обязана с дефолтом БЕЗ сужений - иначе замолчит.

    Замер по сохранённым выдачам: «токийский гуль s1e1» - меню из трёх, и живее всех
    полнометражка «Токийский гуль 2» (2019), которую каталог подписал частью 2. Считайся
    «а не» среди уже суженных, вторая часть выпала бы из сравнения тем же сужением, что
    и из дефолта, взятое сошлось бы само с собой - и картина уехала бы к зрителю молча.
    """
    ghoul = [
        plan("Токийский гуль", 2014, kind="tv", season=1, asked_series=True, pool=[SD]),
        plan("Токийский гуль 2", 2019, part=2, seeders=90, asked_series=True),
        plan("Токийский гуль", 2017, seeders=40, asked_series=True),
    ]

    said = default_note(ghoul, "токийский гуль s1e1")

    assert said == (
        phrase(
            "choice.note_instead_asked_why",
            asked="токийский гуль s1e1",
            mine=f"Токийский гуль (2014{phrase('choice.series_mark')})",
            other="Токийский гуль 2 (2019)",
            why=phrase("choice.why_other_kind"),
        )
    )


def test_the_line_speaks_even_when_the_default_stayed_the_first_menu_item() -> None:
    """🔴 TC-860. Дефолт остался первым пунктом, но сезон себе он не назвал ни разу.

    Ни «Мираж 2», ни «Мираж 3» первого сезона не несут - ни частью, ни именем раздачи, -
    и узкие ворота (:func:`~torrcast.usecases.choice.asked_season.asked_season`)
    отступают к «считаем как считали»: дефолтом молча вставала часть 2, потому что
    хронологически она первая. Молчание строки тут читалось бы как «сезона в меню
    хватило», хотя нужного не было вовсе.
    """
    mirage = [
        plan("Мираж 2", 2018, kind="tv", part=2, season=1, asked_series=True, seeders=90),
        plan("Мираж 3", 2020, kind="tv", part=3, season=1, asked_series=True, seeders=40),
    ]

    said = default_note(mirage, "мираж s1e1")

    assert said == (
        phrase(
            "choice.note_season_asked",
            asked="мираж s1e1",
            mine=f"Мираж 2 (2018{phrase('choice.series_mark')})",
            season=1,
            part=2,
        )
    )


def test_a_carried_season_stays_silent_even_when_the_part_number_differs() -> None:
    """Раздача сама назвала спрошенный сезон - часть тут ни при чём, строки не будет.

    :func:`~torrcast.usecases.choice.asked_season.carries_season` пропускает картину и
    по имени раздачи, не только по части: соврать про подмену там, где сезон named,
    было бы хуже, чем промолчать.
    """
    named = replace(film("Мираж 2 S01 WEB-DL 1080p", seeders=90), season=1)
    mirage = [plan("Мираж 2", 2018, kind="tv", part=2, season=1, asked_series=True, pool=[named])]

    assert default_note(mirage, "мираж s1e1") == ""


def test_every_key_the_line_builds_on_the_fly_exists_in_the_catalog() -> None:
    """🔴 Ключ тут собирается из кусков (``choice.note_instead`` + ``_asked`` + ``_why``).

    Разбор исходников такой ключ не видит: в тексте его нет ни разу. Значит сторожить
    его нечем, кроме как назвать все восемь поимённо - иначе ветка без слов человека
    падала бы `KeyError` ровно у того, кто ответил номером сам.
    """
    tails = ("", "_asked")
    keys = [f"choice.note_instead{tail}" for tail in tails]
    keys += [f"choice.note_instead{tail}_why" for tail in tails]
    keys += [f"choice.note_namesake{tail}" for tail in tails]
    keys += [f"choice.note_season{tail}" for tail in tails]

    assert [key for key in keys if key not in en()] == []
