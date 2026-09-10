"""Файл с договорным словом последнего отказа подъёма - рядом с файлом состояния.

Юнит показа и командная строка - разные процессы, и единственный канал между ними -
диск: тем же путём юнит уже сообщает место посадки показа
(:func:`torrcast.usecases.playback._show_state.mark_landed`). Поэтому слово отказа
пишется файлом рядом с состоянием, там же, где лежат ``facts.json`` и
``release-pins.json``. Контракт и молчаливое умолчание - в порте
(:class:`torrcast.ports.refusal_record.RefusalRecord`), тут только файловая правда.

🔴 Записать и прочитать обязаны мочь оба процесса в любой момент, включая свою смерть:
все три ручки глотают отказы диска целиком. Запись - последняя правда умирающего показа,
и ронять его ради неё самой - значит потерять и причину, и чистый выход.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.ports.refusal_record import RefusalRecord


class FileRefusalRecord(RefusalRecord):
    """Слово отказа файлом ``start-refusal.json`` рядом с состоянием экземпляра."""

    def record(self, reason: str) -> None:
        """Записать договорное слово отказа; пустое слово не записывается вовсе."""
        if not reason:
            return
        with contextlib.suppress(OSError):
            _write_atomic(self._path(), {"reason": reason})

    def read(self) -> str | None:
        """Слово последнего отказа; записи нет или она битая - ``None``."""
        try:
            raw: Any = json.loads(self._path().read_text(encoding="utf-8"))
            reason = raw.get("reason") if isinstance(raw, dict) else None
        except (OSError, ValueError):
            return None
        return reason if isinstance(reason, str) and reason else None

    def forget(self) -> None:
        """Стереть запись: новый подъём взят в работу, прошлый отказ ему не принадлежит."""
        with contextlib.suppress(OSError):
            self._path().unlink(missing_ok=True)

    def _path(self) -> Path:
        """Файл записи: рядом с состоянием, как у недельного следа и памяти подбора.

        Путь перечитывается на каждый зов: ``TORRCAST_STATE`` разводит экземпляры узла
        по своим состояниям, и запись обязана лежать рядом со СВОИМ.
        """
        return state_path().with_name("start-refusal.json")


__all__ = ["FileRefusalRecord"]
