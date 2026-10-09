"""Наши читатели ``/stream``: снятие закрывает вход, но ждёт их естественного конца.

``rem`` под живым читателем роняет TorrServer MatriX.143: его кэш закрывается раньше, чем
обработчик ``/stream`` перестал пользоваться картой кэша. Поэтому снятие сперва запрещает
новые чтения, а :class:`~torrcast.adapters.torrserver.describer.Describer` шлёт ``rem`` только
после конца уже идущих. Учтены и HTTP-ответы, и дочерний ``ffprobe``.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs, urlsplit

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


class StreamReads:
    """Открытые ответы по хэшу раздачи и раздачи, снятые до нового ``add``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._readers: dict[str, int] = {}
        self._closed: set[str] = set()

    @contextmanager
    def reading(self, url: str) -> Iterator[bool]:
        """Встать читателем потока; снятая раздача возвращает ``False`` без чтения."""
        key = _hash_of(url)
        if key is None:
            yield True
            return
        with self._lock:
            live = key not in self._closed
            if live:
                self._readers[key] = self._readers.get(key, 0) + 1
        if not live:
            yield False
            return
        try:
            yield True
        finally:
            with self._lock:
                left = self._readers[key] - 1
                if left:
                    self._readers[key] = left
                else:
                    del self._readers[key]

    @contextmanager
    def opened(self, url: str, open_answer: Callable[[], Any]) -> Iterator[Any]:
        """Открыть HTTP-ответ на учёте; снятая раздача не посылает новый запрос."""
        with self.reading(url) as live:
            if not live:
                yield None
                return
            with open_answer() as answer:
                yield answer

    def close(self, torrent_hash: str) -> bool:
        """Закрыть раздачу для новых читателей; вернуть, есть ли уже идущий."""
        key = torrent_hash.casefold()
        with self._lock:
            self._closed.add(key)
            return self._readers.get(key, 0) > 0

    def busy(self, torrent_hash: str) -> bool:
        """Держит ли наш читатель раздачу открытой прямо сейчас."""
        with self._lock:
            return self._readers.get(torrent_hash.casefold(), 0) > 0

    def reopen(self, torrent_hash: str) -> None:
        """Раздачу добавили заново: читать её снова можно."""
        with self._lock:
            self._closed.discard(torrent_hash.casefold())


def _hash_of(url: str) -> str | None:
    """Хэш раздачи из адреса ``/stream?link=<хэш>&index=..``, иначе ``None``."""
    parts = urlsplit(url)
    if not parts.path.endswith("/stream"):
        return None
    link = parse_qs(parts.query).get("link")
    return link[0].casefold() if link else None


#: Учёт процесса: читатели встают в него, снятие ждёт их окончания.
READS: Final = StreamReads()

__all__ = ["READS", "StreamReads"]
