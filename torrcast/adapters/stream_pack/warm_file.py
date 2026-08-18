"""Греет файл фоном под будущий показ: карта, начало потока и место, откуда играем."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from typing import Any

from torrcast.adapters.stream_pack.container_of import container_of
from torrcast.adapters.stream_pack.film_keys import film_keys
from torrcast.adapters.stream_pack.head_open import head_open
from torrcast.adapters.stream_pack.pull_head import pull_head
from torrcast.adapters.stream_pack.warm_at import warm_at
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.warm_open import HEAD_WARM


def warm_file(
    source_url: str,
    at: float = 0.0,
    alive: Any = None,
    name: str = "",
    *,
    keys_of: Callable[[str], FilmKeys] = film_keys,
    warm: Callable[[str, int, int, Any], int] = warm_at,
) -> None:
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
    """

    def work() -> None:
        keys: FilmKeys | None = None
        with contextlib.suppress(Exception):
            keys = keys_of(source_url)
        if alive is not None and not alive():
            return
        offset = keys.byte_at(at) if keys is not None and at > 0 else 0
        # Контейнер знает карта; у карты из кэша прошлой версии его нет - тогда спрашиваем
        # имя файла раздачи, оно у показа всегда под рукой.
        head = head_open((keys.kind if keys is not None else "") or container_of(name))
        with contextlib.suppress(Exception):
            pull_head(source_url, head if offset else HEAD_WARM, alive, warm=warm)
        if not offset:
            return
        with contextlib.suppress(Exception):
            if alive is None or alive():
                warm(source_url, offset, HEAD_WARM, alive)

    threading.Thread(target=work, daemon=True).start()
