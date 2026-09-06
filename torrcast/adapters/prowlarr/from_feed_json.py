"""Разбирает JSON-ответ ленты последних раздач в строки с датой первой раздачи."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from torrcast.adapters.prowlarr.collect_rows import collect_rows
from torrcast.domain.broadcast_release import _is_broadcast_release
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.infra_error import InfraError


def from_feed_json(payload: Any) -> list[FeedRow]:
    """Разобрать ответ ленты; строка без валидной даты, без hash или трансляция - вон.

    Строки собираются ПО ОДНОЙ (:func:`collect_rows` с одним элементом), а не всей
    пачкой разом: битую строку сборщик молча роняет, и при сборе пачкой даты сдвинулись
    бы относительно укороченного списка результатов.

    Спортивная трансляция (:func:`~torrcast.domain.broadcast_release._is_broadcast_release`)
    отсеивается ЗДЕСЬ, а не в общем разборе выдачи
    (:func:`~torrcast.adapters.prowlarr.to_releases.to_releases`): «кино и сериалы, и
    только они» - требование ленты (ТЗ §9), а спрошенное человеком руками продукт
    отдаёт как есть.
    """
    if not isinstance(payload, list):
        raise InfraError(phrase("prowlarr.unexpected_answer"))
    out: list[FeedRow] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        published = _published(item.get("publishDate"))
        if published is None:
            continue
        title = item.get("title")
        if isinstance(title, str) and _is_broadcast_release(title):
            continue
        rows = collect_rows(
            [
                (
                    item.get("title"),
                    item.get("infoHash"),
                    item.get("size"),
                    item.get("seeders"),
                    item.get("indexer"),
                )
            ]
        )
        if rows:
            out.append(FeedRow(rows[0], published))
    return out


def _published(value: Any) -> datetime | None:
    """Время раздачи из ``publishDate``; молчание или битая строка - ``None``."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


__all__ = ["from_feed_json"]
