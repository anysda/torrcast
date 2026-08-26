"""Чтение снятой карты опорных кадров с полки; полку заводит :mod:`_keys_shelf`."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

from torrcast.adapters.stream_probe.shelf import _touch
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.warm_open import KEYS_RULES


def read_keys(cache: Path) -> FilmKeys | None:
    """Карта с полки или ``None``: битую, пустую, чужую и снятую прежними правилами.

    🔴 Карта, снятую прежними правилами, отсюда НЕ возвращается
    (:data:`~torrcast.domain.warm_open.KEYS_RULES`). Полка живёт дольше правил: у отказа
    срок есть, а принятая карта возвращалась вечно и заново не судилась никогда - то есть
    файл, который сегодняшний разбор отвергает, показу всё равно доставался с полки, и
    сетка строилась по нему. Не прочли - значит, снимем заново (:func:`film_keys`).
    """
    with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
        saved = json.loads(cache.read_text("utf-8"))
        if int(saved.get("rules", 0)) != KEYS_RULES:
            return None
        at = [float(x) for x in saved["keys"]]
        # Кэш прошлой версии смещений не знал: он всё ещё годен для сетки, а грелка
        # позиции без смещений просто не работает - это лучше, чем выбросить карту.
        # Так же и с исковым временем (via): без него предсказание работает по меткам,
        # как до его появления.
        ready = FilmKeys(
            float(saved["duration"]),
            at,
            [int(x) for x in saved.get("bytes", ())],
            str(saved.get("kind", "")),
            tuple(float(x) for x in saved.get("via", ())),
        )
        _touch(cache)  # полка живёт по времени обращения (:func:`_trim`)
        return ready
    return None
