"""След, которого нет: прогон без композиционного корня ничего не пишет."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.ports.json_value import JsonValue


class Silent:
    """Умолчание порта следа: принимает любое событие и не пишет ни байта.

    Сказанное дальше не идёт никуда, а имена стоят как в договоре
    (:class:`Journal`): по ним лента и подставляется вместо этой.
    """

    def emit(self, phase: str, event: str, **fields: object) -> None:
        """Событие принято и не записано."""

    def mark(self, name: str, **facts: JsonValue) -> None:
        """Отметка принята и не записана."""

    def shutdown(self) -> None:
        """Дописывать нечего: писателя не было."""

    def records(self, since: float = 0.0) -> list[dict[str, JsonValue]]:
        """Записей нет ни с какого момента."""
        del since
        return []

    def session_id(self) -> str:
        return ""

    def start_session(self) -> str:
        return ""

    def health(self) -> tuple[bool, float, int]:
        return False, 0.0, 0

    def __getattr__(self, name: str) -> Callable[..., None]:
        """Любое именное событие молчащей ленты - тоже молчание."""
        return lambda *_args, **_facts: None
