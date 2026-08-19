"""Строит сетку сегментов конкретного файла; зовут показ, прогрев и перекод."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from torrcast.adapters.stream_pack.extra_mbit import extra_mbit
from torrcast.adapters.stream_pack.film_keys import film_keys
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.pack_origin import pack_origin
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.hls_settings import HLS_SEGMENT_SECONDS, MAX_SEGMENT_BYTES
from torrcast.domain.infra_error import InfraError


def grid_for(
    source_url: str,
    duration: float,
    step: float = HLS_SEGMENT_SECONDS,
    on_keys: bool = True,
    say: Any = None,
    delivered_mbit: float = 0.0,
    ceiling_mbit: float = 0.0,
    fixed_mbit: float = 0.0,
    cap: float = MAX_SEGMENT_BYTES,
    *,
    keys_of: Callable[[str], FilmKeys] = film_keys,
    origin_of: Callable[[str], float] = pack_origin,
) -> Grid:
    """Сетка для конкретного файла: по опорным кадрам, если карту удалось снять.

    Карта берётся тремя-пятью Range-запросами из индекса контейнера
    (:func:`torrcast.adapters.frames.keyframes.keyframes`) и стоит около секунды: сверх
    головы и самого индекса mkv платит за пробы честности - индекс бывает врун.
    Контейнер незнакомый, индекса в нём нет, индекс врёт об опорности, карта не похожа
    на видео — берём ровную сетку и говорим об этом вслух: молчаливая подмена нарезки —
    ровно то, из-за чего подвис приёмника расследовали
    двое суток.

    ``delivered_mbit`` — сколько Мбит/с уедет на ТВ в среднем по фильму (паспорт ffprobe,
    :attr:`Media.delivered_mbit`), ``ceiling_mbit`` — потолок перекодирования
    (:attr:`torrcast.domain.config.Config.recode_mbit`, ноль — перекодирование выключено). Из них
    считается поправка «контейнер → ТВ» и работает потолок веса сегмента
    (:data:`MAX_SEGMENT_BYTES`) — без них правило потолка вырождается в прежнее.

    ``cap`` — потолок веса одного куска: он у каждого приёмника свой
    (:attr:`torrcast.domain.profile.Profile.max_segment_bytes`), и умолчание тут осторожное.

    ``keys_of`` и ``origin_of`` - карта опорных кадров и начало ленты. Обе стоят
    настоящими, и обе названы параметром, а не именем модуля: карта стоит Range-запросов,
    начало ленты - живого ffprobe, и стенду нужно спросить сетку, не поднимая ни того, ни
    другого. Прежде стенд подменял их атрибутом модуля, то есть знал не договор
    :func:`grid_for`, а порядок имён внутри него.

    ``fixed_mbit`` — сплошной перекод (:data:`RECODE_CODECS`): вес сегмента больше не
    зависит от карты вовсе, потому что на ТВ уезжает не файл, а наш поток с известным
    битрейтом. Карта тут не просто лишняя, а вредная: лёгкий HEVC (1.3 Мбит/с) она
    объявляет лёгким и разрешает 20-секундные куски, а после перекода тот же кусок
    весит столько, сколько мы в него положили.
    """
    began = time.monotonic()
    # Начало ленты - свойство файла, а не способа его нарезать: считается до всякой развилки
    # и уезжает в любую сетку, какой бы из путей ниже ни выбрался (:func:`pack_origin`).
    origin = origin_of(source_url)
    if not on_keys:
        if say:
            say(f"сетка ровно по {step:g} с - так велено настройкой")
        return replace(Grid.uniform(duration, step), origin=origin)
    try:
        found = keys_of(source_url)
    except InfraError as exc:
        if say:
            say(f"сетка ровно по {step:g} с: {exc}")
        return replace(Grid.uniform(duration, step), origin=origin)
    length = duration or found.duration
    if len(found.at) < 3 or found.at[-1] < length * 0.5:
        if say:
            say(f"сетка ровно по {step:g} с: карта опорных кадров не похожа на видео")
        return replace(Grid.uniform(length, step), origin=origin)
    grid = Grid.on_keyframes(
        found.at,
        length,
        step,
        sizes=found.offset,
        extra_mbit=extra_mbit(found, delivered_mbit),
        ceiling_mbit=ceiling_mbit,
        fixed_mbit=fixed_mbit,
        cap=cap,
        origin=origin,
    )
    if say:
        spans = [grid.span(k) for k in range(grid.count)]
        say(
            f"сетка по опорным кадрам: {grid.count} сегментов по {min(spans):.1f}-"
            f"{max(spans):.1f} с, не тяжелее {cap / 1e6:.0f} МБ "
            f"(карта за {time.monotonic() - began:.1f} с)"
        )
    return grid
