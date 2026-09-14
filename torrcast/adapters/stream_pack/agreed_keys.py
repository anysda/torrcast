"""Сверка карты с прогоном, записанная на полку: следующий показ файла её не повторяет.

Устроена как полка начала ленты (:mod:`_origin_shelf`): ключ - URL потока, запись
черновиком и ``replace``, подрезка по времени обращения. Нужна потому, что показ -
отдельный процесс, и пробный прогон ffmpeg платился на каждом показе заново, хотя карта
уже лежала на полке (замер на стенде `.104`: 0.6-2.1 с между раскладкой и сеткой).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
from collections.abc import Callable
from pathlib import Path

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.stream_pack._keys_draft import _keys_draft
from torrcast.adapters.stream_pack.keys_agree import keys_agree
from torrcast.adapters.stream_pack.mapped_start import mapped_start
from torrcast.adapters.stream_probe.shelf import _touch, _trim
from torrcast.domain.film_keys import FilmKeys
from torrcast.ports.journal.slot import journal

#: Сколько сверок держит полка: столько же, сколько карт, запись весит сотню байт.
AGREED_KEPT = 256


def _agreed_cache(source_url: str) -> Path:
    """Где лежит сверка карты этого файла: имя как у карты, каталог соседний."""
    digest = hashlib.sha1(source_url.encode()).hexdigest()[:16]
    return state_path().parent / "agreed" / f"{digest}.json"


def agreed_keys(
    source_url: str,
    at: float,
    keys: FilmKeys,
    *,
    agree: Callable[[str, float, FilmKeys], bool] = keys_agree,
) -> bool:
    """Сошлась ли карта с прогоном на месте ``at``: с полки, если там это место и тот же кадр.

    Полка хранит только «сошлось». Разошедшаяся карта уже отвергнута на своей полке
    (:func:`refuse_keys`), и второй раз сюда не приходит. Запись верна ровно для того места
    и того обещанного кадра, на которых мерили: другая сетка или другая карта файла
    спрашивают прогон заново.
    """
    guess = mapped_start(keys, at)
    if not math.isfinite(guess):
        return agree(source_url, at, keys)
    point = {"source": source_url, "at": round(at, 3), "guess": round(guess, 3)}
    cache = _agreed_cache(source_url)
    with contextlib.suppress(OSError, ValueError):
        if json.loads(cache.read_text("utf-8")) == point:
            _touch(cache)
            journal().mark("карта: сверка с полки", место=round(at, 3))
            return True
    if not agree(source_url, at, keys):
        return False
    with contextlib.suppress(OSError):
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = _keys_draft(cache)
        try:
            tmp.write_text(json.dumps(point), "utf-8")
            tmp.replace(cache)
        finally:
            tmp.unlink(missing_ok=True)
    _trim(cache.parent, AGREED_KEPT)
    return True


__all__ = ["agreed_keys"]
