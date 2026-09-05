"""Сошлась ли карта опорных кадров с фактом по файлу; спрашивает постройка сетки."""

from __future__ import annotations

import bisect
import math
from collections.abc import Callable

from torrcast.adapters.stream_pack._pilot_start import _pilot_start
from torrcast.adapters.stream_pack.mapped_start import mapped_start
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
    start: Callable[..., float] = _pilot_start,
) -> bool:
    """Стоит ли на месте ``at`` тот опорный кадр, который обещает карта. Не мерили - да.

    🔴 Вопрос ровно один: **проехал ли прогон мимо обещанного кадра**. Карта говорит, где
    ffmpeg встанет после ``-ss at`` (:func:`mapped_start`), пробный прогон показывает, где
    он встал (:func:`_pilot_start`). Встал ДАЛЬШЕ обещанного - значит кадров, которые карта
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

    🔴 TC-133. Меряет здесь САМ пробный прогон (:func:`_pilot_start`), а не
    :func:`pack_start`, как было прежде. Прежде разницы не было: pack_start первым же
    вызовом поднимал тот же прогон. Теперь он отвечает по карте - и сверка карты его
    ответом стала сверкой карты с самой собой, то есть вечным «сошлось». Замер репы на
    нарисованной карте (кадры сдвинуты на 3.0 с назад, файл 600 с): ``keys_agree`` через
    pack_start отвечает ``True`` за 0.000 с, через прогон - ``False`` за 0.049 с.

    Цена - один пробный прогон на файл, и он тут единственный на весь показ: упаковка
    (:func:`pack_start`) больше не платит ни одного. Сверка стоит там, где по её итогу
    ещё можно выбрать другую сетку, - и в этом её смысл: промах карты, найденный уже
    нарезкой (:func:`torrcast.usecases.feed_pack.feed_astray._astray`), лечится
    перезаходом, а карта с нарисованными кадрами перезаходом не лечится - по такой сетке
    резать нечем, и менять надо сетку.

    ``start`` - чем меряется место посадки. Доводом, а не именем внутри модуля: настоящий
    замер поднимает ffmpeg на живой раздаче, а здесь меряется само правило сверки. 🔴 Но
    правило это меряется и БЕЗ подмены (``test_a_drawn_map_is_condemned_by_the_real_run``):
    все пробы с подменённым доводом остались бы зелёными и с мёртвым сторожем.
    """
    guess = mapped_start(keys, at)
    if math.isnan(guess):
        return True
    stood = start(source_url, at, timeout)
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
