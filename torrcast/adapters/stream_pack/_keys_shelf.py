"""Полка снятых карт опорных кадров: где лежит карта файла и что с неё читается.

Общая часть :func:`film_keys` и :func:`pack_start`: место захода считается по той же
карте, по которой построена сетка, и лезть за ней в рой второй раз незачем.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

from torrcast.adapters.filesystem.state import state_path
from torrcast.adapters.stream_probe import _touch
from torrcast.domain.film_keys import FilmKeys


def _keys_cache(source_url: str) -> Path:
    """Где лежит снятая карта опорных кадров этого файла.

    Ключ — сам URL потока: в нём hash раздачи и номер файла, то есть ровно то, что
    определяет содержимое. Кэш нужен не ради экономии трафика (4 МБ), а ради времени:
    Cues лежат в хвосте файла, и **первое** чтение этого места стоит роя — замерено
    13.8 с на «Моане» 2016 и 24.4 с на «Моане 2». Второй показ
    того же файла (продолжение с середины — обычное дело) платить это не должен.
    """
    return (
        state_path().parent / "keys" / f"{hashlib.sha1(source_url.encode()).hexdigest()[:16]}.json"
    )


def _read_keys(cache: Path) -> FilmKeys | None:
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
