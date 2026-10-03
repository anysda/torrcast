"""Откуда взять .torrent раздачи: ``downloadUrl`` строки выдачи Prowlarr по infohash.

Магнет строки не меняется: его сравнивают строкой по всему продукту, а ссылка
Prowlarr от поиска к поиску разная. Поэтому ссылка лежит отдельно, ключом служит
infohash. В ссылке ключ Prowlarr, и потому она живёт только в памяти процесса: на диск,
в журнал и в состояние она не попадает.
"""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from typing import Any, Final

#: Ссылок держать не больше: выдача одного поиска - до сотни строк.
CAP: Final = 5000
_HEX: Final = re.compile(r"[0-9a-f]{40}")


class TorrentLinks:
    """Последняя ссылка на .torrent по infohash, общая на процесс."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._links: OrderedDict[str, str] = OrderedDict()

    def remember(self, payload: Any) -> None:
        """Запомнить ссылки на .torrent из сырого ответа Prowlarr (список строк)."""
        if not isinstance(payload, list):
            return
        for item in payload:
            if not isinstance(item, dict):
                continue
            key = item.get("infoHash")
            url = item.get("downloadUrl")
            if not (isinstance(key, str) and isinstance(url, str)):
                continue
            key = key.casefold()
            if _HEX.fullmatch(key) and url.startswith(("http://", "https://")):
                with self._lock:
                    self._links[key] = url
                    self._links.move_to_end(key)
                    while len(self._links) > CAP:
                        self._links.popitem(last=False)

    def link_for(self, torrent_hash: str) -> str | None:
        """Последняя ссылка на .torrent этой раздачи или ``None``."""
        with self._lock:
            return self._links.get(torrent_hash.casefold())


#: Реестр процесса: его кормит разбор выдачи, читает описатель службы раздач.
LINKS: Final = TorrentLinks()

__all__ = ["CAP", "LINKS", "TorrentLinks"]
