"""Зеркало :mod:`torrcast.usecases.choice._pick_plan`: вопрос «Что смотрим?».

Дефолт - та картина, о которой говорят честные строки про смену (:func:`first_alive`),
и цифра в скобках имеет смысл ровно потому, что рядом напечатан список и человек видит,
от чего отказывается.
"""

from __future__ import annotations

import pytest

from tests.usecases.choice.world import Outside, film, parts, plan
from torrcast.domain.not_found_error import NotFoundError
from torrcast.usecases.choice._pick_plan import _pick_plan
from torrcast.usecases.choice.swap_note import swap_note

VHS = film("Cars 2006 DVDRip XviD", seeders=100, codec="XviD", quality=None)


def test_the_menu_is_printed_before_the_question_so_the_number_has_a_meaning() -> None:
    """Список печатается всегда, а последней строкой идёт то, что случится по Enter.

    Строка стоит именно ПЕРЕД вопросом: терминал после длинного вывода показывает его
    хвост, и шапка тридцатипятистрочного меню уезжает за экран вместе с ним.
    """
    world = Outside()
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    picked = _pick_plan(mummy, environment=world)

    assert world.said[0].splitlines() == ["  1. Мумия (1999)", "  2. Мумия (2017)"]
    assert world.said[1] == "Enter - «Мумия (1999)», пункт 1 из 2"
    assert world.asked == [("Что смотрим?", 2, 1)]
    assert picked is mummy[0], "пустой Enter - это дефолт"


def test_the_number_the_person_answered_is_the_picture_that_goes_on() -> None:
    """Ответ номером - это выбор человека, и он исполняется буквально."""
    world = Outside(answers=[2])
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    assert _pick_plan(mummy, environment=world) is mummy[1]


def test_a_single_picture_is_no_choice_and_the_question_is_not_asked() -> None:
    """Одна картина - спрашивать не о чем, а меню всё равно печатается."""
    world = Outside()
    single = parts(("Мумия", 1999, 47))

    assert _pick_plan(single, environment=world) is single[0]
    assert world.asked == []


def test_a_number_named_by_the_flag_replaces_the_question_and_not_the_choice() -> None:
    """``--pick N`` - названный человеком выбор, тот же номер, что стоит у пункта меню.

    Вопрос тогда не задаётся вовсе, и терминал не нужен: молчаливой подмены тут не
    бывает - номер назвал сам человек по списку на экране.
    """
    world = Outside(tty=False)
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    assert _pick_plan(mummy, pick=2, environment=world) is mummy[1]
    assert world.asked == []
    assert world.said[0].splitlines()[1] == "  2. Мумия (2017)", "список всё равно на экране"


def test_a_number_outside_the_list_is_an_honest_error_and_not_a_quiet_first_item() -> None:
    """Номера нет в списке - честная ошибка: тихо взять первый пункт значило бы подменить кино."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    with pytest.raises(NotFoundError, match="подходит картин: 2, номера 5 нет"):
        _pick_plan(mummy, pick=5, environment=Outside())


def test_without_a_terminal_we_refuse_out_loud_and_say_how_to_name_the_picture() -> None:
    """🔴 Спрашивать есть о чём, а терминала нет - отказываемся вслух.

    Тёзка по году - это ДРУГОЙ фильм: разница между «Мумией» 1999 и «Мумией» 2017 не
    оттенок, а не тот вечер. Цифра в скобках имеет смысл ровно потому, что рядом
    напечатан список и человек видит, от чего отказывается; без терминала видеть его
    некому.
    """
    world = Outside(tty=False)
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    with pytest.raises(NotFoundError) as refusal:
        _pick_plan(mummy, asked="мумия", environment=world)

    said = str(refusal.value)
    assert "терминала нет - вслепую не выбираю" in said
    assert "«Мумия»" in said and "--pick N" in said
    assert world.asked == [], "спрашивать было некого, и висеть мы не стали"


def test_a_default_that_would_swap_a_part_of_the_franchise_is_taken_away_entirely() -> None:
    """🔴 TC-373. Дефолта нет вовсе: строка про первую часть, а номер называет человек.

    Вопрос задаётся БЕЗ дефолта - пустой Enter тут не ответ: он включил бы «Тачки 2»
    вместо просимых «Тачек», то есть ровно ту подмену, о которой строка и говорит.
    """
    world = Outside(answers=[3])
    cars = [
        plan("Тачки", 2006, part=1, pool=[VHS]),
        plan("Тачки 2", 2011, part=2, seeders=40),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]

    picked = _pick_plan(cars, asked="тачки", environment=world)

    assert world.said[1].startswith("«Тачки (2006)» не играет")
    assert world.asked == [("Что смотрим?", 3, None)], "дефолта у вопроса нет"
    assert picked is cars[2]
    assert not any(line.startswith("Enter - ") for line in world.said), "обещать Enter нечем"


def test_several_pictures_are_not_a_reason_to_ask_when_the_top_is_the_one_asked() -> None:
    """🔴 Подошло три картины, а спрашивать не о чем: первая часть жива и стоит сверху.

    Список тут не печатается вовсе: меню читают там, где на него отвечают, а перед
    показом, который уже начался, читать его некому. Вместо списка - одна строка про
    решение, и в ней есть ход к соседним частям.
    """
    world = Outside()
    cars = [
        plan("Тачки", 2006, part=1, seeders=66),
        plan("Тачки 2", 2011, part=2, seeders=71),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]

    picked = _pick_plan(cars, asked="тачки", environment=world)

    assert picked is cars[0]
    assert world.asked == [], "вопроса не было"
    assert world.said == [
        "беру «Тачки (2006)» - подошло картин 3; другая: cast releases тачки и --pick N"
    ]


def test_a_picture_the_lines_are_silent_about_needs_no_terminal_either() -> None:
    """Спрашивать не о чем - значит и терминал не нужен: висеть и отказываться не на чем.

    Ровно в этом месте отказ был больнее всего: на стыке серий консоли уже нет, а
    картина есть, и «вслепую не выбираю» означало не показ вместо показа.
    """
    world = Outside(tty=False)
    cars = [
        plan("Тачки", 2006, part=1, seeders=66),
        plan("Тачки 2", 2011, part=2, seeders=71),
    ]

    picked = _pick_plan(cars, asked="тачки", environment=world)

    assert picked is cars[0]
    assert world.said[0].startswith("беру «Тачки (2006)»")


def test_enter_starts_the_picture_the_honest_line_is_about() -> None:
    """🔴 Дефолт у прибора один, и Enter берёт ровно ту картину, про которую сказано.

    Пока Enter брал верх списка, а строка про смену считала дефолт своей меркой, эти
    двое расходились на 23 запросах из 71 сохранённого меню, и на всех 23 строка молчала:
    сверялась она с одной картиной, а печаталась про другую, поэтому сказать ей было
    нечего. Человек жал Enter и получал «Титаник» 1943 года вместо 1997-го - без единого
    слова о том, что картина другая.
    """
    world = Outside()
    titanic = parts(("Титаник", 1943, 1), ("Титаник", 1953, 2), ("Титаник", 1997, 165))

    picked = _pick_plan(titanic, asked="титаник", environment=world)

    assert picked is titanic[2], "пустой Enter - это дефолт"
    assert world.said[-1] == "Enter - «Титаник (1997)», пункт 3 из 3"
    assert world.asked == [("Что смотрим?", 3, 3)]
    assert swap_note(titanic, picked, "титаник") == (
        "спросили «титаник» - беру «Титаник (1997)», а не «Титаник (1943)»: "
        "рой у неё мёртв - сидов 1"
    ), "картина сменилась - и об этом сказано"
