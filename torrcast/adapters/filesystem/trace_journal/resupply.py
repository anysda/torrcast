"""Поля записи ``play/resupply``: раздачу вернули магнитом после аварии источника.

Зовёт её восстановление раздачи, читает разбор ``cast log``."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def resupply(torrent: str, ok: bool) -> None:
    """Раздачу вернули МАГНИТОМ после аварии источника: чью и удалось ли.

    ``torrent`` - хэш нашей раздачи (чужих не трогаем), ``ok`` - вернулась ли она под тем
    же хэшем. Событие про трекеры: URL потока несёт только хэш, и служба, пережившая
    перезапуск, заводит по нему раздачу без трекеров - ноль байт при живом рое.
    """
    emit("play", "resupply", torrent=torrent, ok=ok)
