"""Запускает подачу описания в своём потоке и помнит раздачи, снятые процессом.

``add`` по-прежнему уходит магнетом и возвращается сразу: клик не ждёт добычи.
Поток заводится, только если описание есть на диске или есть ссылка на него.
"""

from __future__ import annotations

import threading
from typing import Final

from torrcast.adapters.prowlarr.torrent_links import LINKS
from torrcast.adapters.torrserver.describe import describe
from torrcast.adapters.torrserver.torrent_http import TorrentHttp
from torrcast.adapters.torrserver.torrent_store import STORE


class Describer:
    """Один поток на раздачу; раздачу, снятую ``drop``/``park``, не трогает."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._closed: set[str] = set()
        self._running: set[str] = set()

    def closed(self, torrent_hash: str) -> None:
        """Раздачу сняли: описание ей больше не подаётся до нового ``add``."""
        with self._lock:
            self._closed.add(torrent_hash.casefold())

    def dropped(self, torrent_hash: str) -> bool:
        with self._lock:
            return torrent_hash.casefold() in self._closed

    def later(self, base_url: str, torrent_hash: str) -> threading.Thread | None:
        """Запустить подачу описания; нет источника или поток уже идёт - ``None``."""
        key = torrent_hash.casefold()
        with self._lock:
            self._closed.discard(key)
            if key in self._running or not (STORE.has(key) or LINKS.link_for(key)):
                return None
            self._running.add(key)
        thread = threading.Thread(target=self._run, args=(TorrentHttp(base_url), key), daemon=True)
        thread.start()
        return thread

    def _run(self, http: TorrentHttp, key: str) -> None:
        try:
            describe(
                key, fetch=http.fetch, stat=http.stat, upload=http.upload, dropped=self.dropped
            )
        finally:
            with self._lock:
                self._running.discard(key)


#: Описатель процесса: его будит ``TorrServer.add``, ему же говорят о снятии раздачи.
DESCRIBER: Final = Describer()

__all__ = ["DESCRIBER", "Describer"]
