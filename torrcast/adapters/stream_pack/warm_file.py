"""Греет файл фоном под будущий показ: карта, начало потока и место, откуда играем."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from typing import Any

from torrcast.adapters.stream_pack._keys_shelf import _keys_cache
from torrcast.adapters.stream_pack.container_of import container_of
from torrcast.adapters.stream_pack.cues_at import cues_at
from torrcast.adapters.stream_pack.film_keys import film_keys
from torrcast.adapters.stream_pack.head_open import head_open
from torrcast.adapters.stream_pack.pack_origin import pack_origin
from torrcast.adapters.stream_pack.pull_head import pull_head
from torrcast.adapters.stream_pack.warm_at import warm_at
from torrcast.adapters.stream_pack.weigh_keys import weigh_keys
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.frames.mkv.ids import CUES_CHUNK
from torrcast.domain.warm_open import HEAD_WARM


def _shelf_pointer(source_url: str) -> FilmKeys | None:
    """Байтовый указатель файла с полки, в том числе карты, отвергнутой по кадрам."""
    return weigh_keys(_keys_cache(source_url))


def warm_file(
    source_url: str,
    at: float = 0.0,
    alive: Any = None,
    name: str = "",
    *,
    keys_of: Callable[[str], FilmKeys] = film_keys,
    warm: Callable[[str, int, int, Any], int] = warm_at,
    origin_of: Callable[[str], float] = pack_origin,
    cues_of: Callable[[str, Any], int | None] = cues_at,
    pointer_of: Callable[[str], FilmKeys | None] | None = None,
    done: threading.Event | None = None,
) -> threading.Event:
    """Прогреть файл фоном: карта опорных кадров, начало потока и место, откуда играем.

    Зовётся с самой ранней секунды, когда известен файл, — пока человек отвечает на
    вопросы. Порядок именно такой: без карты показ не построит сетку и не
    запустит ffmpeg вовсе; начало файла нужно ffmpeg, чтобы вообще открыть вход; а место
    ``at`` — это то, что он прочитает третьим. Не вышло — не беда: показ сделает то же
    самое сам, просто на своём времени.

    ``at > 0`` — продолжение с середины. Там начало файла нужно только на
    заголовок, поэтому его берём куском поменьше (:data:`HEAD_OPEN`, размер зависит от
    контейнера), а основной прогрев уходит туда, где лежит позиция: байтовое смещение
    известно из той же карты.

    ``keys_of`` и ``warm`` - карта опорных кадров и сам прогрев места. Обе названы
    параметром, а не именем модуля: обе ходят в рой, а меряется тут порядок трёх дел и
    размер головы по контейнеру. ``warm`` уезжает и в :func:`pull_head`: прогрев головы и
    прогрев места - одна и та же работа, и на стенде их видит один наблюдатель.
    ``origin_of`` - замер начала ленты: живой ffprobe, стенду не нужный.
    ``cues_of`` - где у mkv индекс: ffmpeg с ``-ss`` читает его вторым, после заголовка;
    чтение головы уступает показу по тому же ``alive``.
    Карта из кэша torrcast хвоста не читает, а кэш TorrServer живёт отдельно, и индекс
    бывал холодным при прогретой закладке: кадр ждал кусок хвоста 7.4 с.
    ``pointer_of`` - байтовый указатель отвергнутой карты с полки: место позиции он знает
    и тогда, когда сетки по карте не будет.

    Возвращает событие «карта снята или отказана»: без карты сетки нет, и отбор в срок
    (:func:`torrcast.usecases.select_bench._bench_in_time._fit`) ждёт его у подмены.
    ``done`` встаёт, когда вся цепочка кончилась: прогрев записей ряда
    (:mod:`web.record_warm`) отмечает по нему прогретую запись.
    """
    mapped = threading.Event()
    if "." in name and not container_of(name):
        # Карту знают только mkv и mp4; чужое имя файла отвечает про неё сразу, а голова из
        # холодного роя, по которой её отказывает разбор, стоила отбору 1.5 с (AVI «Призрака
        # в доспехах»). Разбор идёт и так: его отказ ложится на полку показу.
        mapped.set()

    def work() -> None:
        try:
            chain()
        finally:
            if done is not None:
                done.set()

    def chain() -> None:
        keys: FilmKeys | None = None
        try:
            with contextlib.suppress(Exception):  # не вышло: показ снимет карту сам
                keys = keys_of(source_url)
        finally:
            mapped.set()
        if alive is not None and not alive():
            return
        if keys is None and at > 0:
            # 🔴 Отказ «индекс врёт» отвергает кадры, а не смещения: указатель лежит на полке
            # рядом с вердиктом. Без него запись с закладкой грела 32 МБ начала, а показ
            # «Интерстеллара» 5212 МБ с 5000 с ждал сверку входа и первый кусок из роя 6.5 с.
            with contextlib.suppress(Exception):
                keys = (pointer_of or _shelf_pointer)(source_url)
        offset = keys.byte_at(at) if keys is not None and at > 0 else 0
        # Контейнер знает карта; у карты из кэша прошлой версии его нет - тогда спрашиваем
        # имя файла раздачи, оно у показа всегда под рукой.
        kind = (keys.kind if keys is not None else "") or container_of(name)
        head = head_open(kind)
        with contextlib.suppress(Exception):
            pull_head(source_url, head if offset else HEAD_WARM, alive, warm=warm)
        with contextlib.suppress(Exception):
            live = offset and kind == "mkv" and (alive is None or alive())
            if live and (cues := cues_of(source_url, alive)) is not None:
                warm(source_url, cues, CUES_CHUNK, alive)
        # Голова уже в рою, и ffprobe начала ленты стоит тут долей секунды; показ, отдельный
        # процесс, возьмёт замер с полки (:func:`pack_origin`), а не станет в очередь за своим.
        with contextlib.suppress(Exception):
            if alive is None or alive():
                origin_of(source_url)
        if not offset:
            return
        with contextlib.suppress(Exception):
            if alive is None or alive():
                warm(source_url, offset, HEAD_WARM, alive)

    threading.Thread(target=work, daemon=True).start()
    return mapped
