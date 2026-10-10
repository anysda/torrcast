"""Память магнитов для возврата раздачи после рестарта TorrServer."""

from __future__ import annotations

import threading
from collections.abc import Callable
from functools import partial
from typing import Any


class RestartRecovery:
    """Помнит наш ``add`` и возвращает его перед повтором потерявшего раздачу ``get``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_hash: dict[str, str] = {}

    def remember(self, torrent_hash: str, magnet: str) -> None:
        with self._lock:
            self._by_hash[torrent_hash.casefold()] = magnet

    def forget(self, torrent_hash: str) -> None:
        """Не возвращать снятую раздачу после рестарта службы."""
        with self._lock:
            self._by_hash.pop(torrent_hash.casefold(), None)

    def for_request(
        self, path: str, body: dict[str, Any], add: Callable[[str], object]
    ) -> Callable[[], object] | None:
        torrent_hash = str(body.get("hash", ""))
        if path != "/torrents" or body.get("action") != "get" or not torrent_hash:
            return None
        return partial(self._restore, torrent_hash, add)

    def _restore(self, torrent_hash: str, add: Callable[[str], object]) -> None:
        with self._lock:
            magnet = self._by_hash.get(torrent_hash.casefold(), "")
        if magnet:
            add(magnet)


RECOVERY = RestartRecovery()

__all__ = ["RECOVERY", "RestartRecovery"]
