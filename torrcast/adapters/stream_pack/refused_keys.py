"""Чтение вердикта «карту с этого файла не снять» с полки; пишет его :func:`film_keys`."""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path

from torrcast.adapters.stream_probe.shelf import _touch


def refused_keys(cache: Path, ttl: float) -> str | None:
    """Отказ по этому файлу, если он ещё помнится, иначе ``None``.

    Отказ лежит там же, где легла бы карта, и под тем же именем - тем, что считается по
    адресу потока, то есть по хэшу раздачи и номеру файла в ней: файл на полке один, и
    сказать он может либо «вот карта», либо «карты не будет». Из-за этого отказы не
    переполняют полку: её потолок считает файлы, а не ответы.

    ⚠️ Места вердикт занимает по-разному, и мерить его сотней байт больше нельзя. Отказ
    разбора (:func:`film_keys`) и правда голый - карты не оказалось вовсе. Отказ СЕТКИ
    (:func:`~torrcast.adapters.stream_pack.grid_for.grid_for`) несёт рядом байтовый указатель
    отвергнутой карты и весит столько же, сколько весила она: 179 КБ на «Матрице» 1999 с её
    8065 точками Cues. Это цена профиля тяжести на втором показе того же фильма, и она
    заплачена сознательно - без указателя каждый кусок уходил бы ужатием на месте.

    Карту с такой записи не прочитать
    (:func:`~torrcast.adapters.stream_pack.read_keys.read_keys` молчит на всём, где стоит
    вердикт), и это ровно то, что нужно: вес по ней считают, а режут - нет
    (:func:`~torrcast.adapters.stream_pack.weigh_keys.weigh_keys`).

    ⚠️ Срок считается по записанному времени вердикта, а не по времени файла: полка
    живёт по обращению (:func:`_touch`), и считай мы срок по нему - память об отказе
    продлевалась бы каждым стартом, то есть становилась бы вечной ровно у того фильма,
    который смотрят чаще всех. Отметка обращения при этом всё равно ставится: она решает
    другое - кого полка вытеснит первым (:func:`~torrcast.adapters.stream_probe.shelf._trim`).
    """
    with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
        saved = json.loads(cache.read_text("utf-8"))
        refused = str(saved["refused"])
        if time.time() - float(saved["when"]) < ttl:
            _touch(cache)
            return refused
    return None
