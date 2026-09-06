"""Разобранный запрос к странице: путь, доводы и тело."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from torrcast.domain.json_value import JsonValue


@dataclass(frozen=True, slots=True)
class Request:
    """Что спросили у страницы: путь уже без строки запроса и уже раскодирован."""

    method: str
    path: str
    query: Mapping[str, str]
    body: Mapping[str, JsonValue]
