"""Строит сетку сегментов конкретного файла; зовут показ, прогрев и перекод."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from torrcast.adapters.stream_pack._keys_shelf import _keys_cache
from torrcast.adapters.stream_pack.extra_mbit import extra_mbit
from torrcast.adapters.stream_pack.film_keys import film_keys
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.keys_agree import keys_agree
from torrcast.adapters.stream_pack.pack_origin import pack_origin
from torrcast.adapters.stream_pack.refuse_keys import refuse_keys
from torrcast.adapters.stream_pack.weigh_keys import weigh_keys
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.hls_settings import HLS_SEGMENT_SECONDS, MAX_SEGMENT_BYTES
from torrcast.domain.infra_error import InfraError
from torrcast.domain.keys_tail_gaps import KEYS_TAIL_GAPS
from torrcast.ports.journal.slot import journal


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
    span_cap: float = 0.0,
    *,
    keys_of: Callable[[str], FilmKeys] = film_keys,
    origin_of: Callable[[str], float] = pack_origin,
    agree_of: Callable[[str, float, FilmKeys], bool] = keys_agree,
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
    ``span_cap`` — потолок его ДЛИНЫ, и он тоже свойство приёмника
    (:attr:`torrcast.domain.profile.Profile.max_segment_seconds`); ноль - потолка нет.

    🔴 Снятой карте верят **только после сверки с фактом**
    (:func:`~torrcast.adapters.stream_pack.keys_agree.keys_agree`), и сверка стоит ЗДЕСЬ, а
    не после. Прежде она стояла после - в первом заходе упаковки
    (:func:`~torrcast.adapters.stream_pack.pack_start.pack_start`), - и её вердикт менял
    ровно одно: как дальше искать место захода. Сетка к этому времени была уже построена,
    роздана четырём держателям и не менялась до конца сеанса. Отсюда боевая запись 26-08:
    ``сверка карты с прогоном: сошлось false, карта 18.932, факт 50.917`` - карта
    промахнулась на 32.0 с на первом же куске, файл помечен недоверенным, а сетка
    ``покадрам: true`` на 741 сегмент по этой самой карте осталась сеткой показа до конца
    вечера. Резать по ней нечем: муксер режет только по кадру
    (``-break_non_keyframes 0``), кадра на границе нет, границы пропускаются, и зритель
    платит подвисом. Признанная не сошедшейся карта не имеет права быть сеткой показа -
    поэтому сверка переехала сюда, где по её итогу ещё можно выбрать ровную.

    ``keys_of``, ``origin_of`` и ``agree_of`` - карта опорных кадров, начало ленты и
    сверка карты с фактом. Все три стоят настоящими, и все три названы параметром, а не
    именем модуля: карта стоит Range-запросов, начало ленты - живого ffprobe, сверка -
    пробного прогона ffmpeg, и стенду нужно спросить сетку, не поднимая ничего из этого.
    Прежде стенд подменял их атрибутом модуля, то есть знал не договор :func:`grid_for`,
    а порядок имён внутри него.

    ``fixed_mbit`` — сплошной перекод (:attr:`Profile.recode_codecs`): вес сегмента больше не
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
        # 🔴 Карты для РЕЗА нет, но байтовый указатель для ВЕСА мог остаться на полке:
        # ровно так выглядит ВТОРОЙ показ фильма, чью карту отверг первый
        # (:func:`weigh_keys`). Без него ровная сетка второго показа осталась бы без
        # профиля тяжести, и каждый её кусок пошёл бы ужатием на месте.
        return replace(
            Grid.uniform(duration, step), origin=origin, keys=weigh_keys(_keys_cache(source_url))
        )
    length = duration or found.duration
    if len(found.at) < 3 or found.at[-1] < length * 0.5:
        if say:
            say(f"сетка ровно по {step:g} с: карта опорных кадров не похожа на видео")
        # ⚠️ Указатель отсюда НЕ берётся, и это не забывчивость: отвергнуто тут не одно
        # утверждение про кадры, а сама похожесть записи на карту видео - взвешивать по
        # ней значило бы верить тому же, чему мы только что отказали.
        return replace(Grid.uniform(length, step), origin=origin)
    tail = length - found.at[-1]
    widest = max(b - a for a, b in zip(found.at, found.at[1:], strict=False))
    if tail > widest * KEYS_TAIL_GAPS:
        return _flat(
            source_url,
            f"карта кончается за {tail:.1f} с до конца фильма при самой широкой дыре "
            f"{widest:.1f} с - хвост резать нечем",
            length,
            step,
            origin,
            say,
            found,
        )
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
        span_cap=span_cap,
    )
    # Ту же карту сетка несёт дальше: по ней кодировщик считает вес куска, и второго
    # похода на полку за ней больше нет (:attr:`Grid.keys`).
    grid = replace(grid, keys=found)
    if grid.count > 1 and not agree_of(source_url, grid.start(1), found):
        return _flat(
            source_url,
            "карта опорных кадров разошлась с прогоном по файлу: прогон встал дальше "
            "обещанного кадра, то есть кадров на границах сетки нет",
            length,
            step,
            origin,
            say,
            found,
        )
    if say:
        spans = [grid.span(k) for k in range(grid.count)]
        say(
            f"сетка по опорным кадрам: {grid.count} сегментов по {min(spans):.1f}-"
            f"{max(spans):.1f} с, не тяжелее {cap / 1e6:.0f} МБ "
            f"(карта за {time.monotonic() - began:.1f} с)"
        )
    return grid


def _flat(
    source_url: str,
    why: str,
    length: float,
    step: float,
    origin: float,
    say: Any = None,
    keys: FilmKeys | None = None,
) -> Grid:
    """Ровная сетка вместо негодной карты: вердикт на полку, причина - вслух.

    Вердикт ложится НА МЕСТО карты (:func:`refuse_keys`) не ради экономии запросов, а
    потому, что иначе следующий показ того же фильма снимет ту же карту, признает её
    годной теми же пробами байт и построит по ней ту же сетку: пробы судят индекс, а
    здесь его судил факт по живому файлу. Срок у вердикта свой
    (:data:`~torrcast.domain.warm_open.KEYS_REFUSED`) - ошибиться могли и мы.

    🔴 ``keys`` - та самая отвергнутая карта, и уезжает она в ДВЕ стороны: на полку рядом
    с вердиктом (:func:`refuse_keys`) и в саму ровную сетку (:attr:`Grid.keys`). Отвергнуто
    в ней ровно одно утверждение - «здесь стоит опорный кадр»; пара «время - смещение»
    честная, и вес куска по ней считается так же, как считался бы по принятой карте.
    Молчаливая потеря этого указателя стоила зрителю вдвое: ровная сетка оставалась без
    профиля тяжести (``профиль: 0.0``), кодировщик не брал ни куска впрок, и КАЖДЫЙ кусок
    уезжал через ужатие на месте, посреди которого упаковка замирает
    (:func:`torrcast.adapters.recode.yield_to_shrink._yield_to_shrink`).
    """
    refuse_keys(_keys_cache(source_url), why, keys)
    journal().mark("карта отвергнута сеткой", почему=why)
    if say:
        say(f"сетка ровно по {step:g} с: {why}")
    return replace(Grid.uniform(length, step), origin=origin, keys=keys)
