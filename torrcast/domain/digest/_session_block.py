"""Один сеанс выжимки целиком: шапка, лента событий и итоговая строка со счётчиками.

Зовёт это разбор ленты (:func:`torrcast.domain.digest.digest.digest`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from torrcast.domain.digest._event_line import _event_line
from torrcast.domain.digest._seams import _seams
from torrcast.domain.digest._words import _clock, _hms
from torrcast.domain.json_number import json_number
from torrcast.domain.json_value import JsonValue

#: Что считается в итоговой строке сеанса и как это называется по-русски. Ребуферы
#: печатаются всегда (ноль ребуферов - тоже новость), остальное - только когда было.
_COUNTED: Final = {
    "buffering": "ребуферов",
    "offline": "обрывов сети",
    "resupply": "возвратов раздачи магнитом",
    "dark": "погасаний показа",
    "revive": "воскрешений показа",
    "nudge": "нуджей сторожа",
    "reload": "повторов LOAD",
    "seek": "перемоток",
    "evict": "вытеснений прогрева",
    "skew": "кусков мимо сетки",
}


def _session_block(sid: str, rows: Sequence[Mapping[str, JsonValue]]) -> str:
    """Блок одного сеанса: что искали, что взяли и чем всё кончилось."""
    began = json_number(rows[0].get("at", 0.0))
    lines: list[str] = []
    query = next((r for r in rows if r.get("event") == "query"), None)
    title = query.get("query") if query else None
    head = f"сеанс {sid} · {_clock(began)}"
    if title:
        head += f" · «{title}»"
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
            line += f", всего {phases[name]}"
        lines.append("  " + line)
    counts = {name: sum(1 for r in rows if r.get("event") == name) for name in _COUNTED}
    tail = f"  итог: ребуферов {counts['buffering']}"
    if seams:
        tail += f", стыков источника {len(seams)}"
    for name, word in _COUNTED.items():
        if name != "buffering" and counts[name]:
            tail += f", {word} {counts[name]}"
    end = next((r for r in reversed(rows) if r.get("event") == "session_end"), None)
    if end is not None:
        where = _hms(json_number(end.get("pos", 0.0)))
        dur = json_number(end.get("dur", 0.0))
        watched = end.get("watched")
        state = "досмотрено" if watched else f"остановлено на {where}"
        tail += f"; {state}" + (f" из {_hms(dur)}" if dur and not watched else "")
    lines.append(tail)
    return "\n".join(lines)
