"""Зеркало :mod:`torrcast.usecases.choice._passport`: фоновый паспорт дефолтной картины.

Справка - независимое слово для гейта года выбранной картины. Нужна она лишь к последней
строке перед стартом, поэтому едет фоном, ровно в те секунды, что уходят на меню и
прогрев: путь до меню она не держит.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, outside, parts, plan
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.choice._passport import _passport


def test_a_menu_of_one_picture_never_goes_to_the_reference_at_all() -> None:
    """Одна картина - выбора не было, сверять нечего, и в справку никто не ходит.

    Лишний поход на счастливом однокартинном пути стоит секунд ровно там, где их и
    считают: между запросом и картинкой.
    """
    world = Outside(passport=Origin(title="The Mummy", year=1999))

    with outside(world):
        holder = _passport(parts(("Мумия", 1999, 47)))

        assert world.passports == []
        assert holder.get() == Origin(), "сверять нечего - и паспорт пустой"


def test_the_reference_is_asked_about_the_picture_that_enter_will_start() -> None:
    """Спрашивается дефолтная картина - та самая, которую включит Enter."""
    world = Outside(passport=Origin(title="The Mummy", year=1999))

    with outside(world):
        holder = _passport(parts(("Мумия", 1999, 47), ("Мумия", 2017, 58)))

        assert holder.get() == Origin(title="The Mummy", year=1999)

    assert world.passports == [("Мумия", False)]


def test_the_reference_follows_the_default_and_not_the_first_line_of_the_menu() -> None:
    """🔴 Дефолт стоит не первой строкой - справка едет всё равно про НЕГО.

    Строку про год печатают только дефолту, и справка, добранная про верх списка,
    спрашивала бы про другую картину: у «медведь s2e7» верх - фильм 1938 года, а Enter
    включает сериал 2022-го, и статьи у фильма с сериалом разные.
    """
    world = Outside(passport=Origin(title="The Bear", year=2022))
    bear = [
        plan("Медведь", 1938, seeders=1),
        plan("Медведь", 2022, seeders=124, kind="tv"),
    ]

    with outside(world):
        _passport(bear).get()

    assert world.passports == [("Медведь", True)], "дефолт тут сериал, а верх списка - фильм"


def test_the_type_of_the_picture_is_told_to_the_reference_because_the_articles_differ() -> None:
    """Тип известен из выдачи, и подсказать его надо: у сериала и фильма разные статьи.

    Год выдачи при этом НЕ подсказывается: справка обязана назвать его сама, иначе
    сверять год картины будет не с чем.
    """
    world = Outside(passport=Origin(title="The Bear", year=2022))
    series = [plan("Медведь", 2026, kind="tv", seeders=90), plan("Медведь", 2011, seeders=40)]

    with outside(world):
        _passport(series).get()

    assert world.passports == [("Медведь", True)]


def test_a_reference_that_fell_over_leaves_an_empty_passport_and_not_a_crash() -> None:
    """Справка молчит или падает - показ этого даже не замечает.

    Паспорт нужен одной честной строке, и ронять из-за него вечер нельзя: пустой ответ
    означает «сверять нечем», и год картины остаётся единственным источником.
    """
    world = Outside(passport=None)

    with outside(world):
        holder = _passport(parts(("Мумия", 1999, 47), ("Мумия", 2017, 58)))

        assert holder.get() == Origin()

    assert world.passports == [("Мумия", False)], "поход был, и он не удался"
