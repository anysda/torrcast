"""Наши ответы ``/stream`` по раздачам: снятие рвёт идущие и закрывает раздачу для новых.

🔴 TC-1407. ``rem`` под живым читателем оставляет в TorrServer MatriX.143 вечный цикл
``readOnceAt``: ``waitAvailable`` сперва верит куску (при ResponsiveMode и грязному), и только
потом смотрит, закрыта ли раздача, а закрытое хранилище отдаёт ноль байт. Ждать, пока наше
чтение кончится само, дорого: снятая раздача живёт ещё секунды и ест полосу у выбранной.
Поэтому снятие обрывает наши соединения (:meth:`StreamReads.cut`), обработчик службы уходит
на первой же записи в сокет, а ``rem`` ждёт по ``/cache``, пока служба отпустит читателей.
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
        self._open: dict[str, set[Any]] = {}
        self._closed: set[str] = set()

    @contextmanager
    def opened(self, url: str, open_answer: Callable[[], Any]) -> Iterator[Any]:
        """Открыть ответ и держать его на учёте; снятая раздача - ``None`` без запроса."""
        key = _hash_of(url)
        if key is None:
            with open_answer() as answer:
                yield answer
            return
        with self._lock:
            live = key not in self._closed
        if not live:
            yield None
            return
        with open_answer() as answer:
            with self._lock:
                live = key not in self._closed  # сняли, пока открывали
                if live:
                    self._open.setdefault(key, set()).add(answer)
            if not live:
                yield None
                return
            try:
                yield answer
            finally:
                with self._lock:
                    self._open[key].discard(answer)
                    if not self._open[key]:
                        del self._open[key]

    def cut(self, torrent_hash: str) -> bool:
        """Закрыть раздачу для новых запросов и оборвать идущие; ``True`` - было что рвать."""
        key = torrent_hash.casefold()
        with self._lock:
            self._closed.add(key)
            answers = list(self._open.get(key, ()))
        for answer in answers:
            _shut(answer)
        return bool(answers)

    def reopen(self, torrent_hash: str) -> None:
        """Раздачу добавили заново: читать её снова можно."""
        with self._lock:
            self._closed.discard(torrent_hash.casefold())


def _shut(answer: Any) -> None:
    """Оборвать соединение ответа: наше чтение кончается сразу, служба видит обрыв.

    Сокет берётся копией дескриптора: ``shutdown`` действует на соединение, а закрытие
    копии не трогает ответ, его закроет читающий поток.
    """
    try:
        fd = os.dup(answer.fileno())
    except (OSError, ValueError, AttributeError):
        return  # ответ уже дочитан и закрыт
    with socket.socket(fileno=fd) as sock, suppress(OSError):
        sock.shutdown(socket.SHUT_RDWR)


def _hash_of(url: str) -> str | None:
    """Хэш раздачи из адреса ``/stream?link=<хэш>&index=..``, иначе ``None``."""
    parts = urlsplit(url)
    if not parts.path.endswith("/stream"):
        return None
    link = parse_qs(parts.query).get("link")
    return link[0].casefold() if link else None


#: Учёт процесса: читатели встают в него, снятие (``DESCRIBER.close``) по нему рвёт.
READS: Final = StreamReads()

__all__ = ["READS", "StreamReads"]
