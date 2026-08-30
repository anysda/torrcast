"""Разбор ленты следа в человеческий текст: чем кончился сеанс и что в нём было.

Чистое чтение записей: ни файлов, ни очереди - их держит сам след
(:mod:`torrcast.adapters.filesystem.trace_journal`). Зовёт разбор ``cast log``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.digest._session_block import _session_block
from torrcast.domain.json_number import json_number
from torrcast.domain.json_value import JsonValue


def digest(rows: Sequence[Mapping[str, JsonValue]], limit: int = 3) -> str:
    """Читаемая выжимка последних сеансов: что искали, что взяли, ребуферы и ошибки.

    Сеанс - все записи с одним ``sid``. Каждая серия начинает новый идентификатор через
    :func:`start_session`. Порядок - от свежих; ``limit`` ограничивает число сеансов,
    ``0`` - все.
    """
    if not rows:
        return phrase("digest.no_trace")
    order: list[str] = []
    by_sid: dict[str, list[Mapping[str, JsonValue]]] = {}
    for rec in rows:
        sid = str(rec.get("sid", "?"))
        if sid not in by_sid:
            by_sid[sid] = []
            order.append(sid)
    for rec in rows:
        by_sid[str(rec.get("sid", "?"))].append(rec)
    order.sort(key=lambda s: json_number(by_sid[s][-1].get("at", 0.0)), reverse=True)
    if limit > 0:
        order = order[:limit]
    blocks = [_session_block(sid, by_sid[sid]) for sid in order]
    return "\n\n".join(blocks)
