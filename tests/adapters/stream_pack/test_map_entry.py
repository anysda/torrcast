"""Дала ли карта место ЭТОМУ заходу: вопрос не про доверие к ней, а про её участие."""

from __future__ import annotations

import math
from collections.abc import Iterator

import pytest

from torrcast.adapters.pack_memory import _MAP_LIED
from torrcast.adapters.stream_pack.map_entry import map_entry
from torrcast.adapters.stream_pack.map_lied import map_lied
from torrcast.adapters.stream_pack.map_trusted import map_trusted
from torrcast.domain.film_keys import FilmKeys

#: Опорные кадры каждые две секунды - та же карта, на которой меряется сам заход.
KEYS = FilmKeys(60.0, [round(k * 2.0, 3) for k in range(31)], [k * 4096 for k in range(31)], "mkv")

FILM = "http://торрент/поток"


@pytest.fixture(autouse=True)
def _own_memory() -> Iterator[None]:
    """Снятое доверие помнится на весь процесс; каждой пробе оно достаётся нетронутым."""
    _MAP_LIED.clear()
    yield
    _MAP_LIED.clear()


def test_the_head_of_the_film_is_a_place_the_map_never_gave() -> None:
    """🔴 TC-1309. У головы файла карта молчит, а доверие к ней при этом целое.

    Ровно эта разница и стоила зрителю подгруза: сторож разъезда спрашивал доверие
    (:func:`map_trusted`) и получал «верим», хотя места этому заходу карта не давала
    вовсе. Ниже нуля ffmpeg не пускает dts, метки головы уезжают на кадр-два вперёд
    (замер репы: карта обещает 0.000, факт 0.080), и заход там встаёт сам.
    """
    assert map_trusted(FILM), "стенд собран неверно: доверие к карте обязано быть целым"
    assert math.isnan(map_entry(FILM, 0.0, KEYS)), "карта дала место голове файла"
    assert math.isnan(map_entry(FILM, -3.0, KEYS)), "карта дала место ниже нуля"


def test_a_boundary_inside_the_film_is_a_place_the_map_did_give() -> None:
    """Внутри фильма карта место даёт - иначе сторожу нечего было бы ловить вовсе."""
    assert map_entry(FILM, 20.0, KEYS) == pytest.approx(18.0), "mkv уезжает на предыдущий кадр"


def test_a_map_without_a_film_to_read_it_from_keeps_quiet() -> None:
    """Карты нет - и места нет: предсказывать нечем, а не «предсказано ноль»."""
    assert math.isnan(map_entry(FILM, 20.0)), "карту взяли из ниоткуда"
    assert math.isnan(map_entry(FILM, 20.0, KEYS._replace(kind="ts"))), "у mpegts своё правило"


def test_a_map_that_lied_gives_no_place_even_where_the_rule_holds() -> None:
    """Доверие снято - карта молчит и там, где правило её работает: второго суда не будет."""
    assert not math.isnan(map_entry(FILM, 20.0, KEYS)), "стенд собран неверно"
    map_lied(FILM)
    assert math.isnan(map_entry(FILM, 20.0, KEYS)), "место взято у карты, которой не верят"
