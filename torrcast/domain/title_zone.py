"""Правило title zone; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data.data_2 import (
    _BRACKETS_RE,
    _COLLECTION_CUT_RE,
    _OPEN_BRACKET_RE,
    _RU_CUT_WORDS,
    _TITLE_CUT_RE,
    _TITLE_TAIL_RE,
)
from torrcast.domain.fansub_episode import _fansub_episode


def _title_zone(text: str, span: tuple[int, int] | None) -> tuple[str, bool]:
    fansub = _fansub_episode(text)
    zone = fansub.group("name") if fansub else text[: span[0]] if span else text
    zone = _BRACKETS_RE.sub(" ", zone)
    cut = _TITLE_CUT_RE.search(zone)
    collection = bool(cut and _COLLECTION_CUT_RE.match(cut.group(0)))
    if cut:
        tail = zone[cut.end() :].lstrip()
        if cut.group(0).casefold() in _RU_CUT_WORDS and tail[:1] in ("/", "|"):
            rest = _TITLE_CUT_RE.search(tail)
            zone = zone[: cut.start()] + (tail[: rest.start()] if rest else tail)
        else:
            zone = zone[: cut.start()]
    zone = _OPEN_BRACKET_RE.split(zone)[0]
    if zone.count(".") >= 2 and zone.count(" ") <= 1:
        zone = zone.replace(".", " ")
    zone = _TITLE_TAIL_RE.sub("", zone)
    return (zone.strip(" .-_|,:;/"), collection)


__all__ = ["_title_zone"]
