"""Быстрый кусок карточки плитки, пока круг раздач ещё считается."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, cast

from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from torrcast.domain.spoken_title import spoken_title
from torrcast.runtime.menu_facts import MenuFacts
from web.answer import Answer
from web.card_details import CardDetails
from web.early_picture import early_picture
from web.kin_ahead import KIN_AHEAD
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
#: Приговор обложки карточки (:class:`web.card_poster.CardPoster`): имя картинки и «ещё идёт».
_Poster = Callable[[Picture], tuple[str | None, bool]]


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
                # An unfinished hovered flight queued its requests behind the background, and
                # the flag cannot move them: a click it has no description for yet flies alone.
                hovered = foreground and not facts.foreground
                told = (title, year) in getattr(facts, "found", {})
                if not (hovered and not told and done is not None and not done.is_set()) and (
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


def preview(
    request: Request, key: str, warm: _Warm, related: _Related, poster: _Poster | None = None
) -> Answer | None:
    """Ответить сведениями плитки, не ожидая поиска раздач.

    ``wait=1`` остаётся в preview, пока круг занят фоном: иначе второй GET стоял в
    :meth:`WarmCache.take` за раздачами. Как только круг готов, GET соберёт полную карточку.
    Прогревает круг СТРОКОЙ: прямая ссылка несёт пустой ``query`` (владелец, TC-1334).
    Обложка судится по фактам плитки: без этого прямая ссылка ждала её весь круг раздач
    (5-10 с), хотя приговор с диска готов за 10 мс.
    """
    title = request.query.get("title", "").strip()
    probe = request.query.get("query", "").strip() or title
    if warm.ready(probe) is not None:
        return None
    kind = request.query.get("kind", "")
    year = _year(request.query.get("year", ""))
    if not title or kind not in {"movie", "tv"} or year is None:
        return None
    getattr(warm, "hint", warm.ask)(probe)
    facts = _facts.of(title, year, kind)

    def look() -> tuple[Any, bool, list[JsonValue] | None, list[Any], str | None]:
        fact, told = facts.ready(title, year), facts.answered(title, year)
        kin = _related_of(related, title, kind == "tv", fact, told, year)
        art = poster(Picture(title, year, "tv" if kind == "tv" else "movie")) if poster else None
        return fact, told, kin, getattr(early_picture(probe, key), "releases", []), art and art[0]

    seen = look()
    if request.query.get("wait") == "1":
        before, until = seen, time.monotonic() + PATIENCE
        while time.monotonic() < until:
            _sleep(_TICK)
            if warm.ready(probe) is not None:
                return None  # the circle landed: the full card answers now, not after PATIENCE
            # Справка, родня, обложка и раздачи приходят разными походами. Перемена одной
            # не должна стоять за другой: ``related=None`` оставляет полку частичной.
            if (seen := look()) != before:
                break
    fact, told, kin, early, art = seen
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
        "poster": art,
        "voices": [],
        "resumable": False,
        "label": "",
        "playing": False,
        "seasons": [],
        "related": _others(key, kin),
        "releases_count": len(early),
        "sources_count": CardDetails.sources_count(early),
        "searching": True,
    }
    # Always partial: ``searching`` has no end but the circle, even for a confirmed missing
    # article. A final-looking answer here left such a card on "searching" forever.
    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return Answer(200, encoded, extra=((_PARTIAL, "1"),))


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
    related: _Related, title: str, series: bool, fact: object, told: bool, year: int | None = None
) -> list[JsonValue] | None:
    """Wait for the blurb QID before paying a fallback passport request.

    A related tile already has the QID of the shelf that published it, so its own
    shelf does not wait for the Wikipedia article.  Without any QID a confirmed
    missing article still means no franchise.
    """
    entity = str(getattr(fact, "entity", "")) or ("" if series else KIN_AHEAD.entity(title, year))
    if getattr(fact, "missing", False) and not entity:
        return []
    if entity:
        return cast(list[JsonValue] | None, cast(Any, related).of(title, series, entity))
    if not told:
        return None
    return related.of(title, series)


__all__ = ["preview", "time"]
