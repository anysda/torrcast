"""Зеркало :mod:`torrcast.usecases.choice.first_alive`: картина меню по умолчанию.

Смотреть франшизу начинают с начала, а не с самой обсиженной части: «тачки» - это
просьба про «Тачки» 2006, даже когда сидов больше у «Тачек 3». Мёртвые части при этом
пропускаются, иначе Enter снова упирался бы в пустой рой.
"""

from __future__ import annotations

from tests.usecases.choice.world import film, parts, plan
from torrcast.usecases.choice.first_alive import _first_alive, first_alive

#: Немой VHS-рип: рой у него есть, а годной раздачи нет ни одной.
VHS = film("Moana 1926 DVDRip XviD", seeders=100, codec="XviD", quality=None)


def test_the_default_is_the_first_part_by_chronology_and_not_the_most_seeded_one() -> None:
    """Дефолт - первая по хронологии, а не вожак по сидам.

    Прежний дефолт считался самым живым и на этом ошибался: «тачки» - 66 / 0 / 1 / 121
    сид, и он печатал `[4]`, то есть «Тачки 3» вместо просимых «Тачек».
    """
    cars = parts(("Тачки", 2006, 66), ("Тачки 2", 2011, 1), ("Тачки 3", 2017, 121))

    assert first_alive(cars) == 1


def test_a_part_with_nothing_to_play_is_skipped_instead_of_being_offered() -> None:
    """Замер «моаны»: документалка 1926 года пропускается - годного у неё нет вовсе.

    Не пропусти её - и Enter упирался бы в немой VHS-рип на 0.7 ГБ вместо «Моаны» 2016.
    """
    moana = [
        plan("Моана: романтика золотого века", 1926, pool=[VHS]),
        plan("Моана", 2016, seeders=222),
        plan("Моана 2", 2024, seeders=140),
    ]

    assert first_alive(moana) == 2


def test_liveliness_is_the_pictures_own_swarm_and_not_a_share_of_the_franchise_leader() -> None:
    """Доля от самой живой части была прямой ошибкой, и стоила она классики.

    Замер: «Мумия» 1999 года при живых десятках не дотягивала до четверти от части 2026
    года с сотнями сидов и пропускалась - дефолтом десять прогонов из десяти вставала
    картина, которой человек не называл. То же у «хищника», «дюны» и «джуманджи».
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия возвращается", 2001, 33), ("Мумия", 2026, 300))

    assert first_alive(mummy) == 1


def test_the_type_named_by_the_query_outweighs_a_livelier_namesake_of_another_type() -> None:
    """«хорошая жена s1e1» - это просьба про сериал, и дефолт считается среди сериалов."""
    wife = [
        plan("Хорошая жена", 1987, seeders=40, asked_series=True),
        plan("Хорошая жена", 2015, seeders=18, kind="tv", asked_series=True),
    ]

    assert first_alive(wife) == 2


def test_with_nothing_alive_the_number_still_points_at_the_liveliest_of_its_type() -> None:
    """Живого нет вовсе - отдаём самую живую из картин НАЗВАННОГО типа.

    Выбирать всё равно не из чего, но цифра в скобках обязана на что-то указывать - и
    указывать на полнометражку, когда спросили серию, она при этом не смеет.
    """
    dogs = [
        plan("Великий из бродячих псов", 2012, seeders=100, asked_series=True),
        plan("Великий из бродячих псов", 2016, seeders=2, kind="tv", asked_series=True),
        plan("Великий из бродячих псов", 2019, seeders=4, kind="tv", asked_series=True),
    ]

    assert first_alive(dogs) == 3


def test_counting_among_a_named_few_leaves_the_rest_of_the_menu_out_of_the_question() -> None:
    """:func:`_first_alive` считает среди перечисленных номеров - остальные не в счёт."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58), ("Мумия", 2026, 300))

    assert _first_alive(mummy, [2, 3]) == 2
    assert _first_alive(mummy, []) == 3, "спрашивать не о ком - отвечает самая живая"


def test_a_named_season_keeps_the_default_off_the_part_numbered_otherwise() -> None:
    """🔴 TC-818. Спросили первый сезон - дефолт не садится на вторую часть франшизы.

    Замер по сохранённым выдачам: «код гиас s1e1» после добора ставил дефолтом «Код Гиас:
    Восставший Лелуш 2» (2008), которую сам каталог подписал частью 2, - при живом первом
    сезоне в том же меню. Обе ступени тут работают вместе: вторая часть выбывает по
    спрошенному сезону (:func:`asked_season`), а однораздачный первый сезон не уступает
    дефолт соседке по франшизе (:func:`backed`).
    """
    geass = [
        plan("Код Гиас: Восставший Лелуш 2", 2008, kind="tv", part=2, season=1, asked_series=True),
        plan(
            "Код Гиас: Восставший Лелуш", 2006, kind="tv", seeders=11, season=1, asked_series=True
        ),
        plan(
            "Code Geass: Dakkan no Rozé",
            2024,
            kind="tv",
            season=1,
            asked_series=True,
            pool=[film("e01", seeders=77), film("e02", seeders=13)],
        ),
    ]

    assert first_alive(geass) == 2
