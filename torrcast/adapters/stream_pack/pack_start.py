"""Отвечает, где на самом деле встанет заход после ``-ss``; спрашивает упаковка."""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable

from torrcast.adapters.pack_memory import _SEEK_LOCK, _SEEK_OK
from torrcast.adapters.stream_pack._keys_shelf import _keys_cache
from torrcast.adapters.stream_pack._pilot_start import _pilot_start
from torrcast.adapters.stream_pack.mapped_start import mapped_start
from torrcast.adapters.stream_pack.read_keys import read_keys
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.hls_settings import SPLIT_SLACK
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

    🔴 Но вычисленному верят **только после сверки с фактом**: предсказание проверяется
    пробным прогоном один раз на файл, и лишь потом заходы идут без него. Дешёвая
    «уверенность» тут уже дважды стоила показу правильных кусков — ошибка на один опорный
    кадр уводит все резы захода, и куски лежат под верными именами с чужим содержимым.
    Разошлось больше полукадра — файл помечается недоверенным навсегда, и по нему
    работает прежний пробный прогон.

    ``-muxdelay 0 -muxpreload 0`` обязательны: без них мультиплексор mpegts добавляет
    к меткам свои 1.4 с, и «первый кадр» оказался бы не там, где он есть на самом деле.

    ``pilot`` - сам пробный прогон. Параметром, а не именем внутри модуля: он поднимает
    ffmpeg и ffprobe на живом файле, а здесь меряется правило сверки - сколько раз прогон
    зовут и что запоминают о файле после него.
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
    if not math.isnan(guess):
        with _SEEK_LOCK:
            trusted = _SEEK_OK.get(source_url)
        if trusted:
            journal().mark("заход по карте", просили=round(at, 3), встали=round(guess, 3))
            return guess
    found = pilot(source_url, at, timeout)
    if not math.isnan(guess) and _SEEK_OK.get(source_url) is None:
        agreed = abs(found - guess) <= SPLIT_SLACK
        with _SEEK_LOCK:
            _SEEK_OK[source_url] = agreed
        journal().mark(
            "сверка карты с прогоном",
            сошлось=agreed,
            карта=round(guess, 3),
            факт=round(found, 3),
        )
    return found
