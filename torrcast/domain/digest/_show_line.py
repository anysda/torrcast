"""Строки выжимки про сам показ: куски, план кодирования и всё, что мешало играть.

Ветка отдаёт ``None``, если событие не её: разбор идёт дальше по разборщикам
(:func:`torrcast.domain.digest._event_line._event_line`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.digest._words import _hms
from torrcast.domain.json_number import json_number
from torrcast.domain.json_value import JsonValue
from torrcast.domain.trace_sources import PACKED, WARMED, WARMED_COPY, WARMED_RECODE

#: Решение о кодировании куска - КЛЮЧОМ КАТАЛОГА, а не готовым словом (:func:`plan`):
#: строка эта уезжает человеку и обязана говорить на его языке
#: (:mod:`torrcast.domain.catalogs.digest`).
_PLAN: Final = {"copy": "digest.plan_copy", "recode": "digest.plan_recode"}

#: Как называется источник куска в выжимке; тоже ключи каталога, а не слова.
_SOURCES: Final = {
    PACKED: "digest.src_packed",
    WARMED: "digest.src_warmed",
    WARMED_COPY: "digest.src_warmed_copy",
    WARMED_RECODE: "digest.src_warmed_recode",
}


def _show_line(rec: Mapping[str, JsonValue], stamp: str, seam: bool) -> str | None:
    """Событие показа одной строкой; не его событие - ``None``."""
    event = str(rec.get("event", ""))
    if event == "segment":
        # Каждый кусок в выжимку не печатаем - их сотни; печатаем только смену источника.
        if not seam:
            return ""
        src = str(rec.get("src", ""))
        named = _SOURCES.get(src)
        return phrase(
            "digest.seam",
            stamp=stamp,
            slot=rec.get("slot", "?"),
            src=phrase(named) if named else src,
        )
    if event == "plan":
        spots = rec.get("spots", [])
        if isinstance(spots, list):
            named = ", ".join(str(int(json_number(slot))) for slot in spots)
            tail = phrase("digest.plan_spots", named=named) if named else ""
        else:
            count = int(json_number(spots))
            tail = phrase("digest.plan_spot_count", count=count) if count else ""
        return phrase(
            "digest.plan",
            stamp=stamp,
            pack=_named_plan(rec.get("pack", "")),
            warm=_named_plan(rec.get("warm", "")),
            tail=tail,
        )
    if event == "note":
        return f"{stamp}{rec.get('text', '')}"
    if event == "buffering":
        return phrase("digest.buffering", stamp=stamp, pos=_hms(json_number(rec.get("pos", 0.0))))
    if event == "freeze":
        # Подгруз - потерянная зрителем плёнка, а не слово приёмника: состояние стоит в
        # строке рядом, потому что на приставке оно всё это время «играю».
        pos = json_number(rec.get("pos", 0.0))
        return phrase(
            "digest.freeze",
            stamp=stamp,
            pos=_hms(pos),
            lost=f"{json_number(rec.get('lost', 0.0)):.1f}",
            secs=f"{json_number(rec.get('secs', 0.0)):.0f}",
            state=rec.get("state", "?"),
            front=f"{json_number(rec.get('front', 0.0)) - pos:.0f}",
            total=f"{json_number(rec.get('total', 0.0)):.1f}",
        )
    if event == "offline":
        # Спрошенный источник называется источником: «сеть» тут была бы догадкой, а мы
        # знаем точно - служба ответила (или не ответила) нам сама.
        head = phrase("digest.offline_source" if rec.get("asked") else "digest.offline_net")
        return phrase(
            "digest.offline",
            stamp=stamp,
            head=head,
            why=rec.get("why", phrase("digest.offline_why")),
        )
    if event == "resupply":
        end = phrase("digest.resupply_ok" if rec.get("ok") else "digest.resupply_wait")
        return phrase("digest.resupply", stamp=stamp, end=end)
    if event == "nudge":
        return phrase(
            "digest.nudge",
            stamp=stamp,
            hit=rec.get("hit", 1),
            pos=_hms(json_number(rec.get("pos", 0.0))),
            to=_hms(json_number(rec.get("to", 0.0))),
            stuck=f"{json_number(rec.get('stuck', 0.0)):.0f}",
            front=f"{json_number(rec.get('front', 0.0)) - json_number(rec.get('pos', 0.0)):.0f}",
        )
    if event == "reload":
        error = ""
        if "error" in rec:
            error = (
                phrase("digest.reload_code", error=rec["error"])
                if rec.get("error") is not None
                else phrase("digest.reload_no_code")
            )
        # Исход берётся из ``ok``, и только когда поле вообще названо: у записей старше
        # правки его нет, и молчание о нём честнее выдуманного «не вышло».
        end = (
            ""
            if "ok" not in rec or rec.get("ok")
            else phrase("digest.reload_failed", why=rec.get("why", phrase("digest.why_unnamed")))
        )
        return phrase(
            "digest.reload",
            stamp=stamp,
            pos=_hms(json_number(rec.get("pos", 0.0))),
            error=error,
            tries=rec.get("tries", 1),
            end=end,
        )
    if event == "refetch":
        # Показ тут не гас: приёмник переспросил источник внутри своего терпения. Исход
        # берётся из ``ok``, а не из пустоты ``why``: пустая причина без него значила бы
        # и «перезабор ушёл», и «исход не назвали».
        end = (
            ""
            if rec.get("ok")
            else phrase("digest.refetch_failed", why=rec.get("why", phrase("digest.why_unnamed")))
        )
        return phrase(
            "digest.refetch",
            stamp=stamp,
            pos=_hms(json_number(rec.get("pos", 0.0))),
            tries=rec.get("tries", 1),
            end=end,
        )
    if event == "dark":
        # Поле shown разделяет две разные аварии: погасший показ человек успел
        # посмотреть, а показ без единого кадра - это «включил и не включилось»
        # (:func:`torrcast.adapters.filesystem.trace_journal.dark`). В записях прежних
        # версий поля нет - они все про погасший показ, поэтому умолчание True.
        head = (
            phrase("digest.dark_at", pos=_hms(json_number(rec.get("pos", 0.0))))
            if rec.get("shown", True)
            else phrase("digest.dark_blank")
        )
        return phrase(
            "digest.dark", stamp=stamp, head=head, why=rec.get("why", phrase("digest.dark_why"))
        )
    if event == "revive":
        took = phrase("digest.revive_ok" if rec.get("ok") else "digest.revive_failed")
        return phrase(
            "digest.revive",
            stamp=stamp,
            took=took,
            pos=_hms(json_number(rec.get("pos", 0.0))),
            tries=rec.get("tries", 1),
            waited=f"{json_number(rec.get('waited', 0.0)):.0f}",
        )
    if event == "seek":
        wait = rec.get("wait")
        # Картинки не было вовсе - это отдельный исход, а не нулевое ожидание: нулём его
        # печатала как раз старая метрика, верившая слову приёмника.
        back = (
            phrase("digest.seek_shown", wait=f"{json_number(wait):.1f}")
            if wait is not None
            else phrase("digest.seek_blank", why=rec.get("why", phrase("digest.why_unnamed")))
        )
        return phrase(
            "digest.seek",
            stamp=stamp,
            frm=_hms(json_number(rec.get("frm", 0.0))),
            to=_hms(json_number(rec.get("to", 0.0))),
            back=back,
        )
    return None


def _named_plan(decision: object) -> str:
    """Решение о кодировании словом человека; чужое слово - как есть, знаком вопроса."""
    key = _PLAN.get(str(decision))
    return phrase(key) if key else "?"
