"""Закладки продукта как список экрана «Продолжить»: ``GET /api/history``."""

from __future__ import annotations

import json

from hass.poster_name import poster_name
from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.ports.state_store.slot import store
from web.answer import Answer
from web.request import Request


def history(_request: Request) -> Answer:
    """Недосмотренные закладки, свежайшая сверху; досмотренные до конца - не сюда.

    Источник - тот же :class:`torrcast.domain.watch_state.WatchState`, что и у резюме
    показа: карточка не заводит своего хранилища, а читает то, что уже пишет продукт.
    """
    entries = store().load().entries
    fresh = sorted(entries.items(), key=lambda kv: kv[1].updated, reverse=True)
    items = [_item(key, entry) for key, entry in fresh if not entry.watched]
    return Answer(200, json.dumps({"items": items}, ensure_ascii=False).encode("utf-8"))


def _item(key: str, entry: Entry) -> dict[str, JsonValue]:
    """Одна строка списка: ровно то, что просит вёрстка плитки."""
    return {
        "key": key,
        "title": entry.title,
        "kind": entry.kind,
        "year": entry.year or None,
        "label": entry.label,
        "pos": entry.pos,
        "dur": entry.dur,
        "updated": entry.updated,
        "poster": poster_name(entry.title, entry.year or None, entry.kind),
        "resumable": entry.resumable,
    }
