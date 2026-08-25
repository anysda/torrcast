"""Зеркало :mod:`torrcast.domain.asked_year`: год отдельным словом в конце запроса."""

from torrcast.domain.asked_year import asked_year


def test_a_trailing_year_is_taken_off_the_name() -> None:
    """🔴 TC-777. Год человек берёт из нашего же меню - «(2008, сериал)»."""
    assert asked_year("Байки Мэтра 2008") == ("Байки Мэтра", 2008)
    assert asked_year("Матрица, 1999") == ("Матрица", 1999)


def test_a_year_glued_to_the_name_is_part_of_it() -> None:
    """«2049» в «Бегущем по лезвию 2049» - имя, а не год: отдельным словом оно не стоит."""
    assert asked_year("blade runner2049") == ("blade runner2049", None)


def test_a_name_without_a_year_stays_as_it_was() -> None:
    assert asked_year("Байки Мэтра") == ("Байки Мэтра", None)
    assert asked_year("тачки 2") == ("тачки 2", None)
    assert asked_year("  психо  ") == ("психо", None)
