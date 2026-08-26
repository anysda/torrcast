"""Сошлась ли карта опорных кадров с фактом по файлу; спрашивает постройка сетки."""

from __future__ import annotations

import bisect
import math
from collections.abc import Callable

from torrcast.adapters.stream_pack.mapped_start import mapped_start
from torrcast.adapters.stream_pack.pack_start import pack_start
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.hls_settings import SPLIT_SLACK
from torrcast.domain.hls_wait import PILOT_TIMEOUT
from torrcast.ports.journal.slot import journal


def keys_agree(
    source_url: str,
    at: float,
    keys: FilmKeys,
    timeout: float = PILOT_TIMEOUT,
    *,
    start: Callable[..., float] = pack_start,
) -> bool:
    """Стоит ли на месте ``at`` тот опорный кадр, который обещает карта. Не мерили - да.

    🔴 Вопрос ровно один: **проехал ли прогон мимо обещанного кадра**. Карта говорит, где
    ffmpeg встанет после ``-ss at`` (:func:`mapped_start`), пробный прогон показывает, где
    он встал (:func:`pack_start`). Встал ДАЛЬШЕ обещанного - значит кадров, которые карта
    насчитала между обещанным местом и этим, в файле нет: демуксер не сел ни на один из
    них, потому что садиться там не на что. Карта, у которой кадры нарисованы, - не карта,
    и сетка по ней это не сетка, а список мест, где резать нечем.

    Направление тут не вкус, а замер (18 ГБ, h264, индекс с точкой Cues на каждый
    кластер). 24 пробы вразброс по фильму: **21 встала ВПЕРЁД** обещанного (от +0.5 до
    +73.9 с, проскочено до 61 точки карты), назад - **ни одной**, ровно - 3. Те же пробы
    по первым 16 границам сетки: **15 вперёд из 16**. Единственная проба назад ушла ровно
    на одну точку карты (-1.251 с) - это промах предсказания на кадр
    (:data:`~torrcast.domain.warm_open.SEEK_SHIFT`), а не нарисованный кадр, и отвергать
    из-за него честную карту значило бы платить всем фильмом за один кадр. Поэтому судит
    только уезд ВПЕРЁД, и порог ему - тот же :data:`SPLIT_SLACK`, которым сверяется
    сама посадка.

    ``True`` там, где мерить нечем: карта про это место правила не знает (``nan`` у
    :func:`mapped_start` - чужой контейнер, край карты, самое начало файла). «Не мерили»
    и «сошлось» - разные вещи, но приговором может быть только замер.

    Цена - один пробный прогон в кадр, и он тот же самый, который упаковка заплатит через
    мгновение на первом же заходе: :func:`pack_start` помнит ответ на весь процесс. То
    есть сверка не добавляется к старту, а переезжает в него на шаг раньше - туда, где по
    её итогу ещё можно выбрать другую сетку.

    ``start`` - чем меряется место посадки. Доводом, а не именем внутри модуля: настоящий
    замер поднимает ffmpeg на живой раздаче, а здесь меряется само правило сверки.
    """
    guess = mapped_start(keys, at)
    if math.isnan(guess):
        return True
    stood = start(source_url, at, timeout, keys)
    if stood <= guess + SPLIT_SLACK:
        return True
    ahead = bisect.bisect_left(keys.at, stood - SPLIT_SLACK) - bisect.bisect_right(
        keys.at, guess + SPLIT_SLACK
    )
    journal().mark(
        "прогон проехал мимо кадра карты",
        просили=round(at, 3),
        карта=round(guess, 3),
        факт=round(stood, 3),
        нарисовано=max(ahead, 0),
    )
    return False
