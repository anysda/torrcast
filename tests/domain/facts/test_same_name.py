"""Проверяет строгую мерку имени: ею гейт добора верит справке или не верит."""

from torrcast.domain.facts.same_name import same_name


def test_the_same_name_and_the_almost_the_same_name_are_not_one_yardstick() -> None:
    """🔴 TC-253. Одна буква - то же имя, одно слово из трёх - уже другая картина.

    «Сальтберн» и «Солтберн» - одно имя в двух транскрипциях, и добору по нему верить
    можно. А «Все мы незнакомцы» и «Все мы убийцы» расходятся ровно одним словом из трёх -
    и это картины 2023 и 1952 годов.
    """
    assert same_name("сальтберн", "Солтберн")
    assert same_name("Уэнсдей", "Уэнздей")
    assert same_name("Крики и шёпот", "Шёпоты и крики")
    assert not same_name("Все мы незнакомцы", "Все мы убийцы")
    assert not same_name("мужчина который удивил всех", "Человек, который удивил всех")


def test_a_part_number_is_neither_a_typo_nor_the_whole_franchise() -> None:
    """🔴 TC-338. Номер части в имени - не описка, а часть франшизы - не целое."""
    # Номер части - не описка: разница в одну цифру имени не прощается.
    assert not same_name("Крепкий орешек 2", "Крепкий орешек 3")
    assert not same_name("Крепкий орешек 3", "Крепкий орешек 2")
    assert not same_name("Один дома 2", "Один дома 3")
    assert not same_name("Час пик 2", "Час пик 3")
    # Часть франшизы - не целое: заголовок длиннее спрошенного имени.
    assert not same_name("матрица", "Матрица: Перезагрузка")
    assert not same_name("тачки", "Тачки 4")
    # Само имя при этом не пострадало.
    assert same_name("бен 10", "Бен 10")
    assert same_name("Властелин колец: Братство кольца", "Властелин колец")
    assert same_name("сальтберн", "Солтберн")


def test_a_short_name_is_never_forgiven_one_letter() -> None:
    """У имени из пяти букв одна буква разницы - это уже другое имя."""
    assert not same_name("Психо", "Психи")


def test_two_short_words_ahead_are_a_localized_release_name() -> None:
    """🔴 TC-283. «Все мы незнакомцы» и статья «Незнакомцы» - одно прокатное имя."""
    assert same_name("Все мы незнакомцы", "Незнакомцы")
