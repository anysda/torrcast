"""Имена постера и адрес запасного кадра; зовёт сборщик картинки карточки."""

from __future__ import annotations

from torrcast.adapters.wiki.wiki_spelling import WikiSpelling
from torrcast.domain.facts.near_name import _near_name
from torrcast.domain.facts.read_origin import read_origin
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.domain.transliterate import transliterate
from torrcast.runtime.facts_wiring import FACTS


def _poster_names(shown: PlaybackSnapshot) -> list[str]:
    """Все записанные имена картины, без догадок и повторов."""
    out: list[str] = []
    for name in (shown.title, shown.original, shown.query.replace("-", " ")):
        clean = name.strip()
        if clean and clean.casefold() not in {item.casefold() for item in out}:
            out.append(clean)
    return out


def _wiki_correction(title: str, year: int, kind: str, timeout: float) -> str:
    """Исправленное Википедией имя, только если паспорт подтвердил год и род."""
    spelling = WikiSpelling(FACTS.client)
    pages = spelling.suggested(title, timeout)
    if not pages and transliterate(title).casefold() != title.casefold():
        pages = spelling.suggested(transliterate(title), timeout)
    near = [page for page in pages if _near_name(title, str(page.get("title") or ""))]
    found = read_origin(near, title, trusted=True, series=kind == "tv")
    return found.name if found.year == year else ""


def _manifest(where: str) -> str:
    """Адрес HLS-базы превратить в адрес мастер-манифеста."""
    return where if where.rstrip("/").endswith(".m3u8") else where.rstrip("/") + "/index.m3u8"
