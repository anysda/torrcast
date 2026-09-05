"""Зеркало :mod:`torrcast.adapters.stream_pack.keys_agree`: сошлась ли карта с фактом.

Мера про направление и про цену. Направление: уезд прогона ВПЕРЁД от обещанного кадра -
это нарисованные кадры и приговор карте, уезд назад - промах предсказания на кадр и
поводом к приговору не является. Цена: прогон поднимается один раз и ровно тогда, когда
карта про это место что-то обещала.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import CLIP_KEY_SECONDS, CLIP_SECONDS
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


#: Карта ролика стенда, собранная ИЗ его шага опорных кадров, а не снятая с файла: сверке
#: нужен не точный список кадров, а расхождение списка с файлом. Шаг тут дробный
#: (:data:`CLIP_KEY_SECONDS` - 50 кадров на 24000/1001), и вписывать его от руки нельзя.
CLIP_KEYS = FilmKeys(
    float(CLIP_SECONDS),
    [round(k * CLIP_KEY_SECONDS, 3) for k in range(int(CLIP_SECONDS / CLIP_KEY_SECONDS) + 1)],
    [k * (1 << 16) for k in range(int(CLIP_SECONDS / CLIP_KEY_SECONDS) + 1)],
    "mkv",
)

#: На столько секунд карта ниже обещает кадры РАНЬШЕ, чем они лежат в файле. Половина шага:
#: обещанное место остаётся внутри того же промежутка, а прогон встаёт за ним - то есть
#: ровно тот уезд ВПЕРЁД, который и есть приговор карте.
DRAWN = CLIP_KEY_SECONDS / 2

#: Куда просят зайти: чуть дальше опорного кадра. Ровно на кадр целиться нельзя - округление
#: карты до миллисекунды увело бы просьбу на кадр раньше, и мерилась бы не сверка.
ASK = round(CLIP_KEYS.at[20] + 0.01, 3)


@pytest.mark.ffmpeg
def test_a_drawn_map_is_condemned_by_the_real_run(clip: str) -> None:
    """🔴 TC-133. Сторож жив на БОЕВОЙ проводке: место посадки меряется, а не берётся у карты.

    Ни одна проба выше этого не видит: все они подставляют свой ``start`` и остались бы
    зелёными, даже перестань сверка мерить вовсе. А перестать ей было с чего: прежде замер
    шёл через :func:`torrcast.adapters.stream_pack.pack_start.pack_start`, и с TC-133 тот
    отвечает по самой карте. Замер репы на файле 600 с с картой, сдвинутой на 3.0 с назад:
    сверка через pack_start сказала ``True`` за 0.000 с - то есть сверила карту с ней же, -
    а через пробный прогон ``False`` за 0.049 с.
    """
    drawn = CLIP_KEYS._replace(at=[max(k - DRAWN, 0.0) for k in CLIP_KEYS.at])

    assert keys_agree(clip, ASK, CLIP_KEYS) is True, "честная карта отвергнута"
    assert keys_agree(clip, ASK, drawn) is False, (
        "нарисованные кадры приняты: сверка спросила карту вместо файла"
    )
