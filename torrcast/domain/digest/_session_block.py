"""Один сеанс выжимки целиком: шапка, лента событий и итоговая строка со счётчиками.

Зовёт это разбор ленты (:func:`torrcast.domain.digest.digest.digest`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.digest._event_line import _event_line
from torrcast.domain.digest._seams import _seams
from torrcast.domain.digest._words import _clock, _hms
from torrcast.domain.json_number import json_number
from torrcast.domain.json_value import JsonValue
from torrcast.domain.shrunk_splice_events import (
    SHRUNK,
    SHRUNK_SPLICE_ATTEMPT,
    SHRUNK_SPLICE_NOT_TRIED,
    SHRUNK_SPLICE_WON,
)

#: Что считается в итоговой строке сеанса и КЛЮЧ КАТАЛОГА, которым это зовётся у
#: человека (:mod:`torrcast.domain.catalogs.digest`), а не готовое слово: строка эта
#: уезжает наружу и обязана говорить на его языке. Ребуферы печатаются всегда (ноль
#: ребуферов - тоже новость), остальное - только когда было.
_COUNTED: Final = {
    "buffering": "digest.count_buffering",
    "offline": "digest.count_offline",
    "resupply": "digest.count_resupply",
    "dark": "digest.count_dark",
    "revive": "digest.count_revive",
    "nudge": "digest.count_nudge",
    "reload": "digest.count_reload",
    "refetch": "digest.count_refetch",
    "seek": "digest.count_seek",
    "evict": "digest.count_evict",
    "skew": "digest.count_skew",
}


def _session_block(sid: str, rows: Sequence[Mapping[str, JsonValue]]) -> str:
    """Блок одного сеанса: что искали, что взяли и чем всё кончилось."""
    began = json_number(rows[0].get("at", 0.0))
    lines: list[str] = []
    query = next((r for r in rows if r.get("event") == "query"), None)
    title = query.get("query") if query else None
    head = phrase("digest.session_head", sid=sid, clock=_clock(began))
    if title:
        head += phrase("digest.session_title", title=title)
    lines.append(head)
    seams = {id(rec) for rec in _seams(rows)}
    # Фаза таймлайна повторяется: упаковка заходит на каждый прыжок, тяжёлый кусок - на
    # каждый слот. Печатается ПЕРВАЯ и сказано, сколько их было всего, - иначе одна фаза
    # съедает выжимку так же, как её съели бы куски (:func:`_event_line`, ветка segment).
    phases: dict[str, int] = {}
    for rec in rows:
        if rec.get("phase") == "timeline":
            name = str(rec.get("event", ""))
            phases[name] = phases.get(name, 0) + 1
    shown: set[str] = set()
    for rec in rows:
        name = str(rec.get("event", ""))
        if rec.get("phase") == "timeline":
            if name in shown:
                continue
            shown.add(name)
        line = _event_line(rec, began, seam=id(rec) in seams)
        if not line:
            continue
        if phases.get(name, 1) > 1 and rec.get("phase") == "timeline":
            line += phrase("digest.phase_total", count=phases[name])
        lines.append("  " + line)
    counts = {name: sum(1 for r in rows if r.get("event") == name) for name in _COUNTED}
    tail = "  " + phrase("digest.total", count=counts["buffering"])
    if seams:
        tail += phrase("digest.total_seams", count=len(seams))
    for name, word in _COUNTED.items():
        if name != "buffering" and counts[name]:
            tail += f", {phrase(word)} {counts[name]}"
    shrunk = sum(1 for r in rows if r.get("event") == SHRUNK)
    if shrunk:
        tried = sum(1 for r in rows if r.get("event") == SHRUNK_SPLICE_ATTEMPT)
        won = sum(1 for r in rows if r.get("event") == SHRUNK_SPLICE_WON)
        skipped = sum(
            1 for r in rows if str(r.get("event", "")).startswith(SHRUNK_SPLICE_NOT_TRIED)
        )
        tail += phrase("digest.total_shrunk", shrunk=shrunk, tried=tried, won=won, skipped=skipped)
    end = next((r for r in reversed(rows) if r.get("event") == "session_end"), None)
    if end is not None:
        where = _hms(json_number(end.get("pos", 0.0)))
        dur = json_number(end.get("dur", 0.0))
        watched = end.get("watched")
        state = phrase("digest.watched") if watched else phrase("digest.stopped_at", where=where)
        tail += f"; {state}" + (
            phrase("digest.end_of", dur=_hms(dur)) if dur and not watched else ""
        )
    lines.append(tail)
    return "\n".join(lines)
