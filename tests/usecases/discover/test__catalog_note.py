"""Зеркало :mod:`torrcast.usecases.discover._catalog_note`: чем каталог зовёт слово."""

from __future__ import annotations

from tests.usecases.choice.world import parts, plan
from torrcast.domain.args import Args
from torrcast.usecases.choice.enter_take import enter_take
from torrcast.usecases.discover._catalog_note import _catalog_note


def test_the_word_is_in_the_name_and_the_line_is_not_printed() -> None:
    """«тачки» - в каталоге это «Тачки» человеку не говорит ничего."""
    cars = parts(("Тачки", 2006, 90))

    assert _catalog_note("тачки", cars, Args(query=["тачки"]), "тачки") == ""


def test_the_line_names_the_picture_that_enter_will_take_not_the_head_of_the_menu() -> None:
    """🔴 TC-1064. Строка сверяется с тем же номером, что и взятие, а не с верхом меню.

    Верх меню и дефолт прибора (:func:`~torrcast.usecases.choice.enter_take.enter_take`)
    совпадают не всегда: мёртвый рой у первого пункта уводит взятие ниже, и строка,
    целящаяся в голову списка, называла бы картину, которую человек не получит.
    """
    tales = parts(("Тачки Мультачки: Байки Мэтра", 2006, 0), ("Тачки: Байки Мэтра", 2008, 400))

    note = _catalog_note("байки метра", tales, Args(query=["байки", "метра"]), "байки метра")

    assert "Тачки: Байки Мэтра" in note
    assert "Мультачки" not in note


def test_a_season_reread_keeps_the_catalogue_line_on_the_callers_query() -> None:
    """Перечитанный сезон не даёт строке каталога второго вопроса об одном номере.

    Алиас назвал вторую картину целиком, поэтому запрос без хвостового номера выбрал бы
    её. Исходный запрос ``asked series 2`` номером отключает этот страж и берёт первую.
    Ровно этот исходный запрос остаётся у вызывающего выбора после локального
    ``season_reread``; строка каталога обязана назвать его же картину.
    """
    plans = [
        plan("Earlier series", 2000, kind="tv", asked_series=True, season=2, seeders=40),
        plan("Wanted series", 2020, kind="tv", asked_series=True, season=2, seeders=80),
    ]
    plans[1].picture.aliases = ("asked-series",)
    rewritten = Args(query=["asked", "series", "s2e1"])
    asked = "asked series 2"

    note = _catalog_note("asked series", plans, rewritten, asked)
    taken = plans[enter_take(plans, asked).number - 1].picture

    assert taken.title == "Earlier series"
    assert "Earlier series" in note
    assert "Wanted series" not in note
