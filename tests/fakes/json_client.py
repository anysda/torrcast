"""Отвечает тестам заранее заданным JSON и запоминает параметры запросов."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


def _nothing(host: str, path: str, params: dict[str, str]) -> Any:
    return {}


@dataclass
class FakeJsonClient:
    """``answer`` решает по хосту и параметрам, чем ответить или что бросить."""

    answer: Callable[[str, str, dict[str, str]], Any] = _nothing
    calls: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)

    def get(
        self,
        host: str,
        path: str,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: float,
    ) -> Any:
        self.calls.append((host, path, dict(params)))
        return self.answer(host, path, params)
