"""Записи ленты для зеркал выжимки: ровно то, что кладёт в след :func:`emit`."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue


def rec(event: str, phase: str = "show", **fields: JsonValue) -> dict[str, JsonValue]:
    """Запись ленты: конверт, как у писателя, плюс поля самого события."""
    return {"at": 0.0, "sid": "s", "pid": 1, "phase": phase, "event": event, **fields}
