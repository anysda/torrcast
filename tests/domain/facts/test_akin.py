"""Проверяет сверку заголовка статьи с запросом и признак «продолжений несколько»."""

from typing import Any

from torrcast.domain.facts.akin import _crowded, akin


def test_a_slash_inside_the_heading_does_not_make_it_another_picture() -> None:
    """«ВандаВижн» в русской Википедии подписан «Ванда/Вижн» - это то же имя."""
    assert akin("вандавижн", "Ванда/Вижн")
    assert akin("ВандаВижн", "Ванда/Вижн")
    # Склейка разделителей не должна открывать дорогу однофамильцу.
    assert not akin("восхождение", "Ганнибал: Восхождение")


def test_the_same_words_in_another_order_are_still_the_same_picture() -> None:
    """Классику зовут по памяти: «Крики и шёпот» - это статья «Шёпоты и крики»."""
    assert akin("Крики и шёпот", "Шёпоты и крики")
    assert akin("Семнадцать мгновений весны", "Семнадцать мгновений весны")


def test_a_reshuffled_name_is_not_a_licence_to_take_a_neighbour() -> None:
    """Послабление тесное: слов поровну, каждому пара, и одно слово так не сверяется вовсе.

    Иначе «Восхождение» совпало бы с «Ганнибал: Восхождение», а «Персона» - с «Персонажем»:
    ровно те подмены, ради которых :func:`akin` и написана.
    """
    assert not akin("Восхождение", "Ганнибал: Восхождение")
    assert not akin("Персона", "Персонаж")
    assert not akin("Крики и шёпот", "Крики и шорох")
    assert not akin("Тачки 2", "Тачки 3")


def test_a_longer_heading_counts_only_while_it_is_alone() -> None:
    """Одно продолжение - уточнение имени, а несколько - выбор части наугад."""
    assert akin("кингсман", "Кингсман: Секретная служба")
    assert not akin("кингсман", "Кингсман: Секретная служба", longer=False)


def test_a_crowd_of_continuations_is_a_bare_franchise_name() -> None:
    """«гарри поттер» продолжают три статьи - выбрать из них нечем."""
    parts: list[Any] = [
        {"title": "Гарри Поттер и Орден Феникса (фильм)"},
        {"title": "Гарри Поттер и Принц-полукровка (фильм)"},
        None,
    ]
    assert _crowded("гарри поттер", parts)
    assert not _crowded("гарри поттер", parts[:1])
