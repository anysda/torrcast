"""Добавить раздачу в TorrServer и записать её в его базу, только если её там ещё нет.

🔴 Запись в базу - не одна строка. Служба (MatriX.143, ``server/settings/torrent.go``,
``AddTorrent``) переписывает ВСЕ раздачи базы, каждую своей транзакцией bbolt со сбросом
диска, и держит при этом общий замок, который ждут ``add`` и ``rem`` всех остальных
(``GetTorrentDB`` внутри ``add``, ``RemTorrentDB`` внутри ``rem``). ``add`` с ``save_to_db``
на раздаче, которая уже лежит в базе, ничего в ней не меняет, но стоит каждому соседу по
этому замку: на стенде ``add`` показа ждал 2.4-2.6 с, а снос 3.0 с, пока держатель записей
продлевал свои раздачи раз в несколько секунд.

Поэтому раздача добавляется без записи, а есть ли она в базе, говорит ответ службы: непустое
``data`` раздача берёт из своей записи в базе (``AddTorrent`` в ``server/torr/apihelper.go``)
или из уже сделанного сохранения. Пусто - раздачу видят впервые, и тот же ``add`` повторяется
с записью: кэш раздач переживает перезапуск службы, как и прежде (TC-734).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

#: Как адаптер шлёт запрос службе: путь и тело на входе, разобранный JSON на выходе.
Post = Callable[[str, dict[str, Any]], Any]


def add_once(post: Post, magnet: str) -> Any:
    """Ответ службы на ``add``; в базу раздача пишется, только если её там ещё нет."""
    payload = post("/torrents", {"action": "add", "link": magnet, "save_to_db": False})
    if isinstance(payload, dict) and not payload.get("data"):
        payload = post("/torrents", {"action": "add", "link": magnet, "save_to_db": True})
    return payload


__all__ = ["add_once"]
