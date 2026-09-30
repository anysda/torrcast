"""Закладки продукта как список экрана «Продолжить»: ``GET /api/history``."""

from __future__ import annotations

import json

from hass.hit_posters import hits
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.continue_row import WARM_ROW, continue_row
from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.ports.state_store.slot import store
from web.answer import Answer
from web.record_hold import RECORD_HOLD
from web.request import Request


def _hold_first(keys: list[str]) -> None:
    RECORD_HOLD.touch(load_config().torrserver_url, keys[:WARM_ROW])


#: Первые записи ряда заводятся уже при запросе истории, а не по зову плиток после
#: отрисовки: метаданные холодной раздачи идут из роя 2-20 с, и ранний клик их ждал.
hold_first = _hold_first


def history(_request: Request) -> Answer:
    """Недосмотренные закладки, свежайшая сверху; досмотренные до конца - не сюда.

    Источник - тот же :class:`torrcast.domain.watch_state.WatchState`, что и у резюме
    показа: карточка не заводит своего хранилища, а читает то, что уже пишет продукт.
    """
    entries = store().load().entries
    row = continue_row(entries)
    hold_first(row)
    items: list[JsonValue] = [_item(key, entries[key]) for key in row]
    # «Продолжить» не витрина рекомендаций: новая запись обязана вернуться сразу,
    # даже когда у старых уже есть обложки, а у неё приговор картинки отрицательный.
    # Клиент честно рисует такую плитку типографским блоком. `_covered` годится для
    # ограниченных рекомендаций, где следующая обложка может занять её место, но тут
    # он выбрасывал ровно только что начатую картину из полного списка истории.
    # Приговор спокойный, но впереди фона: холодная полка главной спрашивает свои десятки
    # картин срочно, и фоновый вопрос «Продолжить» стоял за всей её очередью (4.8-15.6 с).
    offered = hits.offer(items, ahead=True)
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
