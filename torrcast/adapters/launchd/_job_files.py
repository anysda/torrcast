"""Где лежат файлы задания показа: его plist и журнал обоих потоков.

У launchd нет ни journald, ни ``--collect``: журнал задания - обычный файл, который
ведётся самим заданием (``StandardErrorPath`` в plist'е), а регистрация переживает
смерть процесса. Поэтому у задания есть файлы, и уборка их - наша. Каталог - временный
каталог владельца: у системного и пользовательского задания он свой, как и области.
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def _plist_path(unit: str) -> Path:
    """Путь plist'а задания: переписывается на каждый запуск, стирается на гашении."""
    return Path(tempfile.gettempdir()) / f"{unit}.plist"


def _log_path(unit: str) -> Path:
    """Путь журнала задания: переживает гашение, чтобы ``why()`` отвечал и о нём."""
    return Path(tempfile.gettempdir()) / f"{unit}.log"
