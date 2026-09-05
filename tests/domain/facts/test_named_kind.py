"""Зеркало :mod:`torrcast.domain.facts.named_kind`: род, которым разведено имя статьи."""

from torrcast.domain.facts.named_kind import named_kind


def test_a_bare_name_says_that_the_picture_has_no_namesake_of_another_kind() -> None:
    """🔴 Пустота тут утверждение, а не незнание.

    Уточнение рода Википедия приписывает ровно тогда, когда голое имя занято тёзкой.
    Голое имя значит, что делить его не с кем, и статья под ним - статья спрошенной
    картины, какого бы рода она ни оказалась. Этим полнометражная антология, раздаваемая
    по новеллам, отличается от чужой картины с тем же именем.
    """
    assert named_kind("Аниматрица") == ""
    assert named_kind("Париж, я люблю тебя") == ""
    assert named_kind("Бэтмен: Рыцарь Готэма") == ""
    assert named_kind("Chernobyl (miniseries)") == "tv"


def test_a_qualified_name_says_the_kind_out_loud() -> None:
    """«Паразиты (фильм)» - имя, разведённое самим разделом: тёзка другого рода есть."""
    assert named_kind("Паразиты (фильм)") == "movie"
    assert named_kind("Паразиты (фильм, 2019)") == "movie"
    assert named_kind("Сталкер (телесериал)") == "tv"
    assert named_kind("Чернобыль (мини-сериал)") == "tv"
    assert named_kind("Аниматрица (мультфильм, 2003)") == "movie"
    assert named_kind("Смешарики (мультсериал, 2004)") == "tv"
    assert named_kind("Parasite (2019 film)") == "movie"
    assert named_kind("Fargo (TV series)") == "tv"


def test_a_qualifier_that_is_not_about_the_kind_is_not_read_as_one() -> None:
    """Уточнений у Википедии много, и род называет не всякое: молчим, а не гадаем.

    🔴 Читается только ПОСЛЕДНЯЯ скобка имени и только целиком. Слово «фильм» внутри
    самого названия («Фильм о фильме») родом статьи не является, и принять его за
    уточнение значило бы объявить разведённым имя, которое Википедия не разводила, -
    то есть отнять постер у картины, стоящей под голым именем.
    """
    assert named_kind("Паразиты") == ""
    assert named_kind("Сталкер (роман)") == ""
    assert named_kind("Дюна (значения)") == ""
    assert named_kind("Титаник (корабль)") == ""
    assert named_kind("Фильм о фильме") == ""
    assert named_kind("Кинофильм") == ""
    assert named_kind("") == ""
