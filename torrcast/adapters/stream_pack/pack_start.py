"""Отвечает, где на самом деле встанет заход после ``-ss``; спрашивает упаковка."""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable

from torrcast.adapters.stream_pack._keys_shelf import _keys_cache
from torrcast.adapters.stream_pack._pilot_start import _pilot_start
from torrcast.adapters.stream_pack.map_trusted import map_trusted
from torrcast.adapters.stream_pack.mapped_start import mapped_start
from torrcast.adapters.stream_pack.read_keys import read_keys
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.hls_wait import PILOT_TIMEOUT
from torrcast.ports.journal.slot import journal


def pack_start(
    source_url: str,
    at: float,
    timeout: float = PILOT_TIMEOUT,
    keys: FilmKeys | None = None,
    *,
    pilot: Callable[[str, float, float], float] = _pilot_start,
) -> float:
    """Куда на самом деле встанет ffmpeg после ``-ss at``: по карте, а иначе пробным прогоном.

    Знать это обязательно: сетка сегментного муксера отсчитывается от **первого пакета
    прогона**, а ``-ss`` уводит ffmpeg на опорный кадр не позже запрошенного места — причём
    не обязательно на ближайший (замерено на «Моане» 2016: ``-ss 66.150``, сама граница —
    опорный кадр, даёт первый кадр 62.688, то есть **через один**).

    Раньше это место каждый раз измеряли: тот же ffmpeg, тот же ``-ss``, один кадр на
    выход. Цена — 0.13 с на локальном файле и до 2.9 с на живой раздаче, и платил её каждый
    копирующий заход: старт показа, каждая перемотка, оба захода прогрева. Между тем карта
    опорных кадров к этому времени уже снята и лежит в кэше, а перемотку демуксера ведёт
    ровно она (:func:`mapped_start`) — то есть место посадки вычислимо.

    Пробный прогон ушёл и с ПЕРВОГО захода тоже (замер репы: 0.029 с на файле в tmpfs,
    0.042 с на петле по http, против 1.6-10.9 мкс у карты). Прежде он стоял тут сверкой -
    один раз на файл, но ровно на пути к первой картинке.

    🔴 Дешёвая «уверенность» стоила показу правильных кусков дважды, и сверка никуда не
    делась: она переехала с предсказания на ФАКТ. Резы захода муксер отмеряет от первого
    пакета, поэтому промах карты выходит наружу измеримо - нарезанное расходится с
    манифестом ровно на промах (замер репы: карта соврала на 4.0 с, ``drift`` вышел
    4.000 с при 0.000-0.006 с у здорового прогона). Увидев такое, лента показа снимает
    доверие карте (:func:`torrcast.adapters.stream_pack.map_lied.map_lied`) и заходит
    заново - уже пробным прогоном, и по этому файлу дальше только им.

    ``-muxdelay 0 -muxpreload 0`` обязательны: без них мультиплексор mpegts добавляет
    к меткам свои 1.4 с, и «первый кадр» оказался бы не там, где он есть на самом деле.

    ``pilot`` - сам пробный прогон. Параметром, а не именем внутри модуля: он поднимает
    ffmpeg и ffprobe на живом файле, а здесь меряется правило выбора - когда прогон зовут
    вовсе, а когда место захода берётся из карты даром.
    """
    if at <= 0:
        return 0.0
    # Карту не ищем, а берём готовую: к первому заходу она уже снята и лежит в кэше (по ней
    # построена сетка). Нет её там - нет и предсказания, и работает прежний пробный прогон;
    # лезть за картой в рой ради экономии на пробном прогоне было бы обменом секунды на
    # секунды.
    if keys is None:
        with contextlib.suppress(Exception):
            keys = read_keys(_keys_cache(source_url))
    guess = mapped_start(keys, at)
    if not math.isnan(guess) and map_trusted(source_url):
        journal().mark("заход по карте", просили=round(at, 3), встали=round(guess, 3))
        return guess
    return pilot(source_url, at, timeout)
