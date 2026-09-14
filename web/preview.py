"""Быстрый кусок карточки плитки, пока круг раздач ещё считается."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, cast

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
#: Сеть может держать источник дольше штатного добора. Пока идёт этот срок, любой
#: partial- или полный ответ присоединяется к одному запросу, а не открывает волну.
_FACT_FLIGHT: Final = 15.0
#: Неудачный добор до долгого наведения не тянем до всего срока полёта, но быстрый
#: клик не открывает второй поход рядом с ещё догоняющим источником.
_FAILED_RETRY: Final = 3.0
_sleep: Callable[[float], None] = time.sleep


class _Related(Protocol):
    """Кэш родни, способный назвать готовность фонового добора."""

    def of(self, title: str, series: bool) -> list[JsonValue] | None: ...

    def waiting(self, title: str, series: bool) -> bool: ...


class _Warm(Protocol):
    """Круги раздач, которые preview только проверяет и ставит в очередь."""

    def ready(self, query: str) -> object | None: ...

    def ask(self, screen: Sequence[str]) -> int: ...


@dataclass
class _FactFlights:
    """Один незаконченный добор справки на плитку для всех её long-poll запросов."""

    pending: dict[tuple[str, int, str], tuple[MenuFacts, float]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def of(self, title: str, year: int, kind: str, foreground: bool = True) -> MenuFacts:
        """Взять текущий добор или начать ровно один вместо волны клонов."""
        key = title, year, kind
        now = time.monotonic()
        with self.lock:
            active = self.pending.get(key)
            if active is not None and now - active[1] < _FACT_FLIGHT:
                facts = active[0]
                done = getattr(facts, "_done", None)
                if (
                    done is None
                    or not done.is_set()
                    or facts.answered(title, year)
                    or now - active[1] < _FAILED_RETRY
                ):
                    if foreground:
                        facts.foreground = True
                    return facts
            facts = MenuFacts([key], budget=PATIENCE)
            facts.foreground = foreground
            facts.start()
            self.pending[key] = facts, now
            return facts


_facts = _FactFlights()


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
    hint = getattr(warm, "hint", warm.ask)
    hint(request.query["query"])
    series = kind == "tv"
    facts = _facts.of(title, year, kind)
    fact = facts.ready(title, year)
    told = facts.answered(title, year)
    kin = [] if getattr(fact, "missing", False) else _related_of(related, title, series, fact, told)
    if request.query.get("wait") == "1":
        before = (fact, told, kin)
        until = time.monotonic() + PATIENCE
        while time.monotonic() < until:
            _sleep(_TICK)
            fact = facts.ready(title, year)
            told = facts.answered(title, year)
            kin = (
                []
                if getattr(fact, "missing", False)
                else _related_of(related, title, series, fact, told)
            )
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
        # Пустой ответ кэша уже означает, что источник подтвердил отсутствие статьи.
        # Оставлять его скелетом до круга раздач делало законное отсутствие похожим на
        # зависший добор и задерживало карточку на весь поиск.
        "blurb": fact.about or ("" if told else None),
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
    # Confirmed absence finishes both facts and the related shelf.  The release circle
    # may still be loading, but it cannot turn this particular card into a description
    # or a franchise, so asking the page to poll again only creates an empty loop.
    extra = () if getattr(fact, "missing", False) else ((_PARTIAL, "1"),)
    return Answer(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), extra=extra)


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


def _related_of(
    related: _Related, title: str, series: bool, fact: object, told: bool
) -> list[JsonValue] | None:
    """Wait for the blurb QID before paying a fallback passport request."""
    entity = str(getattr(fact, "entity", ""))
    if entity:
        return cast(list[JsonValue] | None, cast(Any, related).of(title, series, entity))
    if not told:
        return None
    return related.of(title, series)


__all__ = ["preview", "time"]
