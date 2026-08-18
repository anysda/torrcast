"""След, которого нет: прогон без композиционного корня ничего не пишет."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.ports.json_value import JsonValue


class Silent:
    """Умолчание порта следа: принимает любое событие и не пишет ни байта."""

    def emit(self, phase: str, event: str, **fields: object) -> None:
        return None

    def mark(self, name: str, **facts: JsonValue) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def records(self, since: float = 0.0) -> list[dict[str, JsonValue]]:
        return []

    def session_id(self) -> str:
        return ""

    def start_session(self) -> str:
        return ""

    def health(self) -> tuple[bool, float, int]:
        return False, 0.0, 0

    def __getattr__(self, name: str) -> Callable[..., None]:
        """Любое именное событие молчащей ленты - тоже молчание."""
        return lambda *args, **fields: None
