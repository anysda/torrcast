"""Состояние просмотра в файле: чтение, атомарная запись и ничего больше.

Правила «что спрашивают у состояния» живут в домене; отсюда его берут показ и хранилище."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState


@dataclass(slots=True)
class State(WatchState):
    """Состояние просмотра, прочитанное из файла и в файл же записываемое.

    Правила «что спрашивают у состояния» - в :class:`~torrcast.domain.watch_state.
    WatchState`; здесь остаётся ровно файл: чтение, атомарная запись и путь к нему.
    """

    @classmethod
    def load(cls) -> State:
        """Прочитать состояние; отсутствующий или битый файл — пустое состояние."""
        try:
            raw: Any = json.loads(state_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        return cls({str(k): Entry.from_json(v) for k, v in raw.items() if isinstance(v, dict)})

    def save(self) -> None:
        _write_atomic(state_path(), {k: asdict(v) for k, v in self.entries.items()})
