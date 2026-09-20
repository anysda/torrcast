"""Дала ли карта опорных кадров место ЭТОМУ заходу; спрашивают упаковка и лента показа."""

from __future__ import annotations

import contextlib
import math

from torrcast.adapters.stream_pack._keys_shelf import _keys_cache
from torrcast.adapters.stream_pack.map_trusted import map_trusted
from torrcast.adapters.stream_pack.mapped_start import mapped_start
from torrcast.adapters.stream_pack.read_keys import read_keys
from torrcast.domain.film_keys import FilmKeys


def map_entry(source_url: str, at: float, keys: FilmKeys | None = None) -> float:
    """Куда карта сажает заход на ``at``; ``nan`` - места она не давала вовсе.

    Правило одно на двоих, и потому вынесено сюда. Спрашивает его сам заход
    (:func:`torrcast.adapters.stream_pack.pack_start.pack_start`) - ему нужно место; и
    спрашивает сторож разъезда (:func:`torrcast.usecases.feed_pack.feed_astray._astray`) -
    ему нужен сам ФАКТ участия карты, потому что лечение у него ровно одно: снять с карты
    доверие и зайти заново. Заход, которому карта места не давала, таким лечением не
    лечится, а цену за попытку платит зритель.

    🔴 Прежде сторож судил по :func:`map_trusted` - «верим ли карте на этом файле», - и
    это не тот вопрос. Верить карте можно и там, где её не спрашивали: у ГОЛОВЫ файла
    место захода не берут из карты никогда (:func:`mapped_start` отвечает там ``nan``:
    ffmpeg не пускает dts ниже нуля и сдвигает метки на кадр-два вперёд, замер репы -
    карта обещает 0.000, факт 0.080). Замер стенда за 8 суток: 86 заходов по карте, и у
    всех ``просили > 0``; 61 заход в слот 0, и ни одного по карте. Все 5 тревог разъезда
    за те же сутки пришлись на слот 0 - то есть ровно туда, где карты не было, - а на 55
    заходов со слотом больше нуля не пришлось ни одной.

    Карта не ищется, а берётся готовой - той же, по которой построена сетка: лезть за ней
    в рой ради ответа было бы обменом секунды на секунды.
    """
    if keys is None:
        with contextlib.suppress(Exception):
            keys = read_keys(_keys_cache(source_url))
    guess = mapped_start(keys, at)
    if math.isnan(guess) or not map_trusted(source_url):
        return math.nan
    return guess
