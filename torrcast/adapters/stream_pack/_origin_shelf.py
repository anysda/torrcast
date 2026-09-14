"""Полка замеров начала ленты: провал ffprobe ниже нуля на файл, рядом с полкой карт.

Устроена как полка карт опорных кадров (:mod:`_keys_shelf`, :func:`film_keys`): ключ -
URL потока, запись черновиком и ``replace``, подрезка по времени обращения. Нужна она
потому, что память :data:`~torrcast.adapters.pack_memory._ORIGIN` живёт в процессе, а
показ - отдельный процесс: без полки ffprobe начала ленты платился на каждом показе
(замер на стенде `.104`: 2.2-4.3 с из пяти секунд до LOAD).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
from pathlib import Path

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.stream_pack._keys_draft import _keys_draft
from torrcast.adapters.stream_probe.shelf import _touch, _trim

#: Сколько замеров держит полка: столько же, сколько карт, запись весит сотню байт.
ORIGIN_KEPT = 256


def _origin_cache(source_url: str) -> Path:
    """Где лежит замер начала ленты этого файла: имя как у карты, каталог соседний."""
    digest = hashlib.sha1(source_url.encode()).hexdigest()[:16]
    return state_path().parent / "origin" / f"{digest}.json"


def _read_origin(source_url: str) -> float | None:
    """Провал ленты ниже нуля с полки, секунды; ``None`` - нет, битая или чужая запись.

    Чужая - та, чей URL не совпал с ключом: у имени шестнадцать знаков хэша, а неверное
    начало ленты стоит мёртвого показа, так что промах тут дешевле веры.
    """
    with contextlib.suppress(OSError, ValueError, KeyError, TypeError, AttributeError):
        cache = _origin_cache(source_url)
        saved = json.loads(cache.read_text("utf-8"))
        slack = float(saved["slack"])
        if saved["source"] != source_url or not math.isfinite(slack) or slack < 0:
            return None
        _touch(cache)
        return slack
    return None


def _keep_origin(source_url: str, slack: float, kept: int = ORIGIN_KEPT) -> None:
    """Положить измеренный провал на полку; осечка записи - не беда, это кэш."""
    cache = _origin_cache(source_url)
    with contextlib.suppress(OSError):
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = _keys_draft(cache)
        try:
            tmp.write_text(json.dumps({"source": source_url, "slack": slack}), "utf-8")
            tmp.replace(cache)
        finally:
            tmp.unlink(missing_ok=True)
    _trim(cache.parent, kept)
