"""Читает диапазоны файла по HTTP; разбор контейнера выполняет домен."""

import http.client
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.swarm_silent_error import SwarmSilentError
from torrcast.domain.why import why
from torrcast.ports.journal.slot import journal


class HttpRangeReader:
    """Range-запросы к одному URL со счётчиком полученных байтов."""

    def __init__(
        self,
        url: str,
        timeout: float = 120.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.url = url
        self.timeout = timeout
        self._opener = opener
        self.taken = 0
        self.requests = 0

    def read(self, offset: int, size: int) -> bytes:
        """Байты ``[offset, offset + size)``; каждый заход с его ожиданием - в след.

        Цена карты - это не байты, а ожидание роя в каждом месте файла, и места у неё
        разные: голова, хвост с индексом, пробы честности. Без отметки на запрос след
        показывал одно окно «чтение -> снята» и приписать его было нечему: замер волны
        30-09 списал такое окно на пробы, а раскладка по запросам показала голову и хвост.
        """
        began = time.monotonic()
        request = urllib.request.Request(
            self.url, headers={"Range": f"bytes={offset}-{offset + size - 1}"}
        )
        try:
            with self._opener(request, timeout=self.timeout) as answer:
                data: bytes = answer.read()
        # ⚠️ Оборванное тело ответа - тоже молчание роя, а не поломка прибора:
        # служба закрывает поток на полуслове, когда куска у неё так и не оказалось,
        # и ``http.client`` роняет это отдельной ветвью, мимо ``OSError``.
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
            raise SwarmSilentError(phrase("frames.head_unreadable", reason=why(exc))) from exc
        self.taken += len(data)
        self.requests += 1
        journal().mark(
            "карта: запрос",
            мб=offset >> 20,
            кб=len(data) >> 10,
            мс=round((time.monotonic() - began) * 1000),
        )
        return data
