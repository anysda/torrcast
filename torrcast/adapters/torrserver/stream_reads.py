"""Наши читатели ``/stream``: снятие закрывает вход, но ждёт их естественного конца.

``rem`` под живым читателем роняет TorrServer MatriX.143: его кэш закрывается раньше, чем
обработчик ``/stream`` перестал пользоваться картой кэша. Поэтому снятие сперва запрещает
новые чтения, а :class:`~torrcast.adapters.torrserver.describer.Describer` шлёт ``rem`` только
после конца уже идущих. Учтены и HTTP-ответы, и дочерний ``ffprobe``.
"""

from __future__ import annotations

import os
import socket
import threading
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs, urlsplit

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


class StreamReads:
    """Открытые ответы по хэшу раздачи и раздачи, снятые до нового ``add``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._readers: dict[str, int] = {}
        self._answers: dict[str, set[Any]] = {}
        self._closed: set[str] = set()
        self._stopped: set[str] = set()

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
                key = _hash_of(url)
                if key is None:
                    yield answer
                    return
                with self._lock:
                    stopped = key in self._stopped
                    if not stopped:
                        self._answers.setdefault(key, set()).add(answer)
                if stopped:
                    _shut(answer)
                    yield None
                    return
                try:
                    yield answer
                finally:
                    with self._lock:
                        self._answers[key].discard(answer)
                        if not self._answers[key]:
                            del self._answers[key]

    def close(self, torrent_hash: str) -> bool:
        """Закрыть раздачу для новых читателей; вернуть, есть ли уже идущий."""
        key = torrent_hash.casefold()
        with self._lock:
            self._closed.add(key)
            return self._readers.get(key, 0) > 0

    def busy(self, torrent_hash: str) -> bool:
        """Держит ли наш читатель раздачу открытой прямо сейчас."""
        with self._lock:
            key = torrent_hash.casefold()
            return key not in self._stopped and self._readers.get(key, 0) > 0

    def stop(self, torrent_hash: str) -> None:
        """Оборвать зависшие наши чтения после срока ожидания.

        HTTP-ответы получают ``shutdown`` сокета. ``ffprobe`` спрашивает
        :meth:`stopped` между короткими ``communicate`` и завершает себя. После этого
        ``Describer`` всё ещё ждёт пустой ``/cache`` перед ``rem``.
        """
        key = torrent_hash.casefold()
        with self._lock:
            self._stopped.add(key)
            answers = list(self._answers.get(key, ()))
        for answer in answers:
            _shut(answer)

    def stopped(self, url: str) -> bool:
        """Был ли срок чтения этого ``/stream`` исчерпан."""
        key = _hash_of(url)
        if key is None:
            return False
        with self._lock:
            return key in self._stopped

    def reopen(self, torrent_hash: str) -> None:
        """Раздачу добавили заново: читать её снова можно."""
        with self._lock:
            key = torrent_hash.casefold()
            self._closed.discard(key)
            self._stopped.discard(key)


def _shut(answer: Any) -> None:
    """Оборвать ответ, не закрывая объект за читающим потоком."""
    try:
        fd = os.dup(answer.fileno())
    except (OSError, ValueError, AttributeError):
        return
    with socket.socket(fileno=fd) as sock, suppress(OSError):
        sock.shutdown(socket.SHUT_RDWR)


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
