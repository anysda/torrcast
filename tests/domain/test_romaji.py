"""Зеркало :mod:`torrcast.domain.romaji`: японское имя кириллицей и его латиница."""

from torrcast.domain.romaji import romaji


def test_a_japanese_name_in_cyrillic_is_spelled_the_way_releases_sign_it() -> None:
    """🔴 TC-963. Побуквенный транслит даёт `sudzu` и ноль строк, Хепбёрн - `suzu` и 24."""
    assert romaji("Каэдэ и Судзу") == "kaede to suzu"


def test_the_conjunction_returns_to_the_connector_it_translated() -> None:
    """Союз «и» стоит на месте と, и в подписи раздачи он пишется словом `to`."""
    assert romaji("Сэн и Тихиро") == "sen to chihiro"


def test_the_everyday_spelling_with_e_is_the_same_name() -> None:
    """Бытовая запись пишет «е» там, где Поливанов пишет «э»."""
    assert romaji("Кимецу но Яйба") == "kimetsu no yaiba"


def test_a_doubled_consonant_is_the_japanese_pause() -> None:
    assert romaji("Хоккайдо но онна") == "hokkaido no onna"


def test_a_russian_phrase_is_not_a_romanization() -> None:
    """Гейт второго захода держится: русское слово спотыкается на первом же месте."""
    russian = (
        "крики и шёпоты",
        "Американская фабрика",
        "Заброшенный дом",
        "все мы незнакомцы",
        "Колыма - родина нашего страха",
        "Двадцать шагов до славы",
        "Супер размер меня",
    )

    assert [romaji(title) for title in russian] == [""] * len(russian)


def test_a_query_that_is_not_pure_cyrillic_is_left_alone() -> None:
    """Латиница и цифры разбираются своими правилами, а не этим."""
    assert romaji("Kaede to Suzu") == ""
    assert romaji("13-я поправка") == ""
