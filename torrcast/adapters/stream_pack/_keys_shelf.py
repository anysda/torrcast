"""Полка снятых карт опорных кадров: где лежит карта файла.

Общая часть :func:`film_keys` и :func:`pack_start`: место захода считается по той же
карте, по которой построена сетка, и лезть за ней в рой второй раз незачем. Читает её с
полки сосед (:func:`~torrcast.adapters.stream_pack.read_keys.read_keys`).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from torrcast.adapters.filesystem.state import state_path


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
