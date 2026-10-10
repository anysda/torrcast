"""Чем прогрев меряет диск: вес прогретого, давность показа, место раздела и способ выкладки.

Зовёт их каталог прогретого (:class:`torrcast.usecases.warm.vault.Vault`), и только он.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from pathlib import Path

from torrcast.usecases.warm.settings import META


def _disk_free(root: Path) -> int:
    """Сколько байт свободно на разделе, где лежит корень прогретого; беда - ноль."""
    try:
        stat = os.statvfs(root)
    except OSError:
        return 0
    return stat.f_bavail * stat.f_frsize


# Имя полки - ключ показа, шестнадцать знаков sha1 во всех формах ключа
# (:mod:`torrcast.usecases.warm.warm_key`, :mod:`torrcast.usecases.warm.key_form`).
_KEY = re.compile(r"[0-9a-f]{16}")


def _shelf(path: Path) -> bool:
    """Каталог, который завёл склад: с именем-ключом или с паспортом. Нечитаемое чужое
    (``lost+found`` под ``nobody`` в контейнере) - не полка, а не повод ослепнуть на все."""
    try:
        return path.is_dir() and (_KEY.fullmatch(path.name) is not None or (path / META).is_file())
    except OSError:
        return False


def _dirs(root: Path) -> list[Path]:
    """Полки склада (:func:`_shelf`).

    Имя спасает полку, чей паспорт не записался на полном разделе. Чужое в корне - не
    полка: на отдельном разделе там лежит ``lost+found``, и вытеснитель не вправе ни
    считать его, ни сносить.
    """
    try:
        return [path for path in root.iterdir() if _shelf(path)]
    except OSError:
        return []


def _touched(path: Path) -> float:
    try:
        return (path / META).stat().st_mtime
    except OSError:
        return 0.0


def _field(where: Path, name: str) -> str:
    """Поле паспорта каталога строкой; нет паспорта, не читается, нет поля - пусто.

    Три разных «нет» сведены в одно намеренно: каждый читающий сверяет прочитанное со
    своим, и пустое у него значит ровно одно - каталог клали до того, как поле начали
    записывать, то есть прежней сборкой.
    """
    with contextlib.suppress(OSError, ValueError):
        found = json.loads((where / META).read_text(encoding="utf-8"))
        if isinstance(found, dict):
            return str(found.get(name, ""))
    return ""


def _title(path: Path) -> str:
    """Название вытесняемого показа из его паспорта; нет паспорта - пустая строка."""
    return _field(path, "title")


def _lay(where: Path) -> str:
    """Способ, которым положены точечные куски каталога, из его паспорта.

    Сверяется со способом этого прогрева (:data:`torrcast.usecases.warm.settings.SPOT_LAY`).
    Пусто - паспорта нет, он не читается или способа в нём не сказано; всё это значит одно:
    каталог клали до того, как способ начали записывать.
    """
    return _field(where, "lay")


def _form(where: Path) -> str:
    """Отпечаток формы ключа, которым каталог заводили, из его паспорта.

    Сверяется с отпечатком этой сборки (:data:`torrcast.usecases.warm.key_form.KEY_FORM`).
    Разошлись - каталог не найдётся больше ни по одному ключу этой сборки
    (:func:`torrcast.usecases.warm.strip_forms.strip_forms`).
    """
    return _field(where, "form")


def _spot_marks(where: Path) -> list[int]:
    """Места, у которых стоит метка точечного перекода, по возрастанию.

    Метка ``v{N}.rec`` и есть след способа выкладки: копию точечная работа не трогала, и
    после смены способа перекладывать надо ровно помеченные места.
    """
    found: list[int] = []
    with contextlib.suppress(OSError):
        for mark in where.glob("v*.rec"):
            with contextlib.suppress(ValueError):
                found.append(int(mark.stem[1:]))
    return sorted(found)


def _size(path: Path) -> int:
    """Вес файла; не прочли - ноль. Ноль тут безопасен: кусок, пропавший между глобом и
    ``stat``, отдача уже переживает (404 → приёмник просит снова)."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _weigh(where: Path) -> int:
    total = 0
    with contextlib.suppress(OSError):
        for suffix in ("ts", "m4s"):
            for path in where.rglob(f"v*.{suffix}"):
                with contextlib.suppress(OSError):
                    total += path.stat().st_size
    return total
