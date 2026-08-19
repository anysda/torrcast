"""Чтение снятой карты опорных кадров с полки; полку заводит :mod:`_keys_shelf`."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

from torrcast.adapters.stream_probe.shelf import _touch
from torrcast.domain.film_keys import FilmKeys


def read_keys(cache: Path) -> FilmKeys | None:
    """Карта с полки или ``None``: битую, пустую и чужую отличаем молча."""
    with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
        saved = json.loads(cache.read_text("utf-8"))
        at = [float(x) for x in saved["keys"]]
        # Кэш прошлой версии смещений не знал: он всё ещё годен для сетки, а грелка
        # позиции без смещений просто не работает - это лучше, чем выбросить карту.
        ready = FilmKeys(
            float(saved["duration"]),
            at,
            [int(x) for x in saved.get("bytes", ())],
            str(saved.get("kind", "")),
        )
        _touch(cache)  # полка живёт по времени обращения (:func:`_trim`)
        return ready
    return None
