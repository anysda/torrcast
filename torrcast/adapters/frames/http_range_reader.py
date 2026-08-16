"""Читает диапазоны файла по HTTP; разбор контейнера выполняет домен."""

import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from torrcast.domain.infra_error import InfraError
from torrcast.domain.why import why


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
        request = urllib.request.Request(
            self.url, headers={"Range": f"bytes={offset}-{offset + size - 1}"}
        )
        try:
            with self._opener(request, timeout=self.timeout) as answer:
                data: bytes = answer.read()
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise InfraError(f"не читается голова файла: {why(exc)}") from exc
        self.taken += len(data)
        self.requests += 1
        return data
