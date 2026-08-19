"""Порядок последней показанной таблицы раздач: файл рядом с состоянием."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.domain.info_hash import info_hash
from torrcast.domain.release import Release


class ReleasePins:
    """Что стояло под номером в таблице ``cast releases``: записать и спросить.

    Номер живёт ровно до следующей таблицы того же запроса, поэтому файл переписывается
    целиком, а не дополняется: показанное вчера под номером 2 сегодня значит другое.
    """

    def remember(self, query: str, releases: dict[str, list[Release]]) -> None:
        """Атомарно запомнить порядок последней таблицы этого запроса."""
        shown = {
            key: [info_hash(release) for release in ranked] for key, ranked in releases.items()
        }
        _write_atomic(self._path(), {query: shown})

    def recalled(self, query: str, picture: str, number: int) -> str:
        """Вернуть хэш, стоявший под номером в последней показанной таблице.

        Номера нет, файла нет, лежит чужое - пусто: по пустому имени показ ищет заново,
        а не берёт раздачу наугад.
        """
        saved = self._read(self._path()).get(query, {})
        ranked = saved.get(picture, []) if isinstance(saved, dict) else []
        if not isinstance(ranked, list) or not all(isinstance(item, str) for item in ranked):
            return ""
        return ranked[number - 1] if 1 <= number <= len(ranked) else ""

    def _path(self) -> Path:
        return state_path().with_name("release-pins.json")

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}


#: Один файл на процесс: и печать таблицы, и разбор номера спрашивают его же.
pins: Final = ReleasePins()
