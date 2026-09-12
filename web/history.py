"""Закладки продукта как список экрана «Продолжить»: ``GET /api/history``."""

from __future__ import annotations

import json

from hass.hit_posters import hits
from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.ports.state_store.slot import store
from web.answer import Answer
from web.request import Request
from web.shelf_tiles import _covered


def history(_request: Request) -> Answer:
    """Недосмотренные закладки, свежайшая сверху; досмотренные до конца - не сюда.

    Источник - тот же :class:`torrcast.domain.watch_state.WatchState`, что и у резюме
    показа: карточка не заводит своего хранилища, а читает то, что уже пишет продукт.
    """
    entries = store().load().entries
    fresh = sorted(entries.items(), key=lambda kv: kv[1].updated, reverse=True)
    items: list[JsonValue] = [_item(key, entry) for key, entry in fresh if not entry.watched]
    offered = _covered(hits.offer(items), len(items))
    public = [_public(item) for item in offered if isinstance(item, dict)]
    return Answer(200, json.dumps({"items": public}, ensure_ascii=False).encode("utf-8"))


def _item(key: str, entry: Entry) -> dict[str, JsonValue]:
    """Одна строка списка: ровно то, что просит вёрстка плитки.

    ``shown`` - имя ДЛЯ ЧЕЛОВЕКА (:attr:`torrcast.domain.entry.Entry.spoken`); ``query``
    остаётся исходным ключом поиска, которым карточка снова собирает свой круг.
    ``original`` нужен только приговору обложки и наружу не выходит.
    """
    return {
        "key": key,
        "title": entry.title,
        "query": entry.query or entry.title,
        "original": entry.original or None,
        "shown": entry.spoken,
        "kind": entry.kind,
        "year": entry.year or None,
        "label": entry.label,
        "pos": entry.pos,
        "dur": entry.dur,
        "updated": entry.updated,
        "resumable": entry.resumable,
    }


def _public(item: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Убрать служебное имя до ответа: оно нужно только поиску картинки."""
    return {key: value for key, value in item.items() if key != "original"}
