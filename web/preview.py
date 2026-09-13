"""Быстрый кусок карточки плитки, пока круг раздач ещё считается."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from typing import Final, Protocol

from torrcast.domain.json_value import JsonValue
from torrcast.domain.spoken_title import spoken_title
from torrcast.runtime.menu_facts import MenuFacts
from web.answer import Answer
from web.rating_score import rating_score
from web.request import Request

_PARTIAL = "X-Torrcast-Partial"
#: Долгий переспрос ждёт независимые от круга источники не дольше секунды. Первый ответ
#: не ждёт вовсе: имя, обложка и скелет должны появиться до Wikipedia/Wikidata.
PATIENCE: Final = 1.0
_TICK: Final = 0.05
_sleep: Callable[[float], None] = time.sleep


class _Related(Protocol):
    """Кэш родни, способный назвать готовность фонового добора."""

    def of(self, title: str, series: bool) -> list[JsonValue] | None: ...

    def waiting(self, title: str, series: bool) -> bool: ...


class _Warm(Protocol):
    """Круги раздач, которые preview только проверяет и ставит в очередь."""

    def ready(self, query: str) -> object | None: ...

    def ask(self, screen: Sequence[str]) -> int: ...


def preview(request: Request, key: str, warm: _Warm, related: _Related) -> Answer | None:
    """Ответить сведениями плитки, не ожидая поиска раздач.

    ``wait=1`` остаётся в preview, пока круг занят фоном. Иначе второй GET попадал в
    :meth:`WarmCache.take` и стоял за раздачами, хотя Wikipedia и Wikidata уже ехали
    отдельно. Как только круг готов, следующий GET соберёт полную карточку.
    """
    if warm.ready(request.query.get("query", "")) is not None:
        return None
    title = request.query.get("title", "").strip()
    kind = request.query.get("kind", "")
    year = _year(request.query.get("year", ""))
    if not title or kind not in {"movie", "tv"} or year is None:
        return None
    warm.ask([request.query["query"]])
    series = kind == "tv"
    facts = MenuFacts([(title, year, kind)], budget=PATIENCE)
    facts.start()
    fact = facts.ready(title, year)
    told = facts.answered(title, year)
    kin = related.of(title, series)
    if request.query.get("wait") == "1":
        before = (fact, told, kin)
        until = time.monotonic() + PATIENCE
        while time.monotonic() < until:
            _sleep(_TICK)
            fact = facts.ready(title, year)
            told = facts.answered(title, year)
            kin = related.of(title, series)
            # Справка и родня приходят разными походами. Перемена одной не должна
            # стоять за другой: ``related=None`` оставляет полку частичной.
            if (fact, told, kin) != before:
                break
    body: dict[str, JsonValue] = {
        "pick": 0,
        "title": title,
        "shown": request.query.get("shown", "") or spoken_title(title, ""),
        "original": None,
        "year": year,
        "kind": kind,
        "runtime": 0.0,
        "runtime_estimated": False,
        "rating": rating_score(fact.rating),
        # Плитка может назвать картину не тем именем, которое круг уточнит потом.
        # Поэтому preview не говорит «нет описания» даже после пустого ответа: только
        # полный ответ по картине вправе подтвердить его отсутствие.
        "blurb": fact.about if told and fact.about else None,
        "poster": None,
        "voices": [],
        "resumable": False,
        "label": "",
        "playing": False,
        "seasons": [],
        "related": _others(key, kin),
        "releases_count": 0,
        "sources_count": 0,
        "searching": True,
    }
    return Answer(
        200, json.dumps(body, ensure_ascii=False).encode("utf-8"), extra=((_PARTIAL, "1"),)
    )


def _year(value: str) -> int | None:
    """Год из строки маршрута, только правдоподобное целое."""
    try:
        year = int(value)
    except ValueError:
        return None
    return year if 1800 <= year <= 3000 else None


def _others(key: str, related: list[JsonValue] | None) -> list[JsonValue] | None:
    """Не ставить открытую плитку в её же полку франшизы."""
    if related is None:
        return None
    return [tile for tile in related if not isinstance(tile, dict) or tile.get("key") != key]


__all__ = ["preview"]
