"""Зеркало :mod:`torrcast.usecases.discover._catalog_note`: чем каталог зовёт слово."""

from __future__ import annotations

from tests.usecases.choice.world import parts
from torrcast.domain.args import Args
from torrcast.usecases.discover._catalog_note import _catalog_note


def test_the_word_is_in_the_name_and_the_line_is_not_printed() -> None:
    """«тачки» - в каталоге это «Тачки» человеку не говорит ничего."""
    cars = parts(("Тачки", 2006, 90))

    assert _catalog_note("тачки", cars, Args(query=["тачки"])) == ""


def test_the_line_names_the_picture_that_enter_will_take_not_the_head_of_the_menu() -> None:
    """🔴 TC-1064. Строка сверяется с тем же номером, что и взятие, а не с верхом меню.

    Верх меню и дефолт прибора (:func:`~torrcast.usecases.choice.enter_take.enter_take`)
    совпадают не всегда: мёртвый рой у первого пункта уводит взятие ниже, и строка,
    целящаяся в голову списка, называла бы картину, которую человек не получит.
    """
    tales = parts(("Тачки Мультачки: Байки Мэтра", 2006, 0), ("Тачки: Байки Мэтра", 2008, 400))

    note = _catalog_note("байки метра", tales, Args(query=["байки", "метра"]))

    assert "Тачки: Байки Мэтра" in note
    assert "Мультачки" not in note
