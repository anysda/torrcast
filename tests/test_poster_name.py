"""Зеркало :mod:`hass.poster_name`: одно имя картины на полку и на маршрут картинки."""

from hass.poster_name import poster_name


def test_a_namesake_of_another_year_or_kind_is_another_picture() -> None:
    """Постер соседки хуже, чем никакого: год и род входят в само имя картинки."""
    assert poster_name("Матрица", 1999, "movie") != poster_name("Матрица", 2021, "movie")
    assert poster_name("Паразиты", 2019, "movie") != poster_name("Паразиты", 2019, "tv")


def test_no_year_reads_the_same_whichever_emptiness_came() -> None:
    """У снимка показа на месте года стоит ноль, у записи выдачи - ничего.

    Без сведения это были бы две записи про одну картину на общей полке, и человек
    увидел бы в списке не ту картинку, что потом заиграет.
    """
    assert poster_name("Тачки", 0, "movie") == poster_name("Тачки", None, "movie")


def test_the_name_is_a_fingerprint_and_not_the_title_itself() -> None:
    """Имя уезжает в адрес: двоеточия и кавычки русского названия в нём - чужая беда."""
    name = poster_name("Возвращение к источнику: Философия и «Матрица»", 2004, "movie")
    assert name.isalnum() and name.isascii(), f"в адрес поехало имя {name!r}"
    assert len(name) == 16
