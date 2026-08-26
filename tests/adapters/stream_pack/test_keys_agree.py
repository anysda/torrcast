"""Зеркало :mod:`torrcast.adapters.stream_pack.keys_agree`: сошлась ли карта с фактом.

Мера про направление и про цену. Направление: уезд прогона ВПЕРЁД от обещанного кадра -
это нарисованные кадры и приговор карте, уезд назад - промах предсказания на кадр и
поводом к приговору не является. Цена: прогон поднимается один раз и ровно тогда, когда
карта про это место что-то обещала.
"""

from __future__ import annotations

from typing import Any

from torrcast.adapters.stream_pack.keys_agree import keys_agree
from torrcast.domain.film_keys import FilmKeys

URL = "http://торрент/поток"

#: Шаг опорных кадров - 1.251 с, как у измеренного вруна; числа входа считаются ОТ него,
#: а не вписываются: на ровных 24 и 25 к/с целый класс не рождается никогда.
STEP = 1.251
KEYS = FilmKeys(
    60.0, [round(k * STEP, 3) for k in range(41)], [k * (1 << 20) for k in range(41)], "mkv"
)


def _stood(where: float) -> Any:
    """Пробный прогон, который всегда встаёт в названное место, и счётчик его подъёмов."""
    runs: list[float] = []

    def start(url: str, at: float, timeout: float = 0.0, keys: Any = None) -> float:
        runs.append(at)
        return where

    return start, runs


def test_a_run_that_stood_where_the_map_promised_keeps_the_map() -> None:
    """Карта обещала кадр, прогон встал на нём - спорить не о чем."""
    at = round(KEYS.at[8] + STEP / 2, 3)
    start, runs = _stood(KEYS.at[8])

    assert keys_agree(URL, at, KEYS, start=start) is True
    assert runs == [at], "прогон обязан подняться ровно один раз и ровно на это место"


def test_a_run_that_drove_past_the_promised_frame_condemns_the_map() -> None:
    """🔴 Прогон встал ДАЛЬШЕ обещанного - кадров между обещанным местом и этим в файле нет.

    Замер на живой раздаче (18 ГБ, h264, точка Cues на каждый кластер): 21 проба из 24
    вразброс по фильму встала вперёд, на первых 16 границах сетки - 15 из 16, уезд от
    +0.5 до +73.9 с.
    """
    at = round(KEYS.at[8] + STEP / 2, 3)
    start, _ = _stood(KEYS.at[20])

    assert keys_agree(URL, at, KEYS, start=start) is False


def test_a_run_that_stood_one_frame_earlier_is_not_a_verdict() -> None:
    """Уезд НАЗАД - промах предсказания на кадр, и честную карту за него не отвергают.

    Единственная проба назад в замере ушла ровно на одну точку карты (-1.251 с). Отвергни
    мы карту за это - платил бы весь фильм за один кадр.
    """
    at = round(KEYS.at[8] + STEP / 2, 3)
    start, _ = _stood(KEYS.at[6])

    assert keys_agree(URL, at, KEYS, start=start) is True


def test_a_map_that_promises_nothing_here_is_not_measured() -> None:
    """«Не мерили» и «сошлось» - разные вещи, но приговором может быть только замер.

    Карта про это место правила не знает (край карты, чужой контейнер, самое начало
    файла) - прогон тут не поднимается вовсе, и приговора не выносится.
    """
    start, runs = _stood(0.0)

    assert keys_agree(URL, KEYS.at[-1] + 100.0, KEYS, start=start) is True
    foreign = FilmKeys(KEYS.duration, KEYS.at, KEYS.offset, "ts")
    assert keys_agree(URL, 10.0, foreign, start=start) is True
    assert runs == [], "прогон подняли там, где карта ничего не обещала"
