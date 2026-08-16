"""Правило unchaptered; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.chapter_of import _chapter_of
from torrcast.domain.picture import Picture


def _unchaptered(pictures: list[Picture]) -> list[Picture]:
    chaptered = {
        chapter[0]
        for picture in pictures
        for release in picture.releases
        if (chapter := _chapter_of(release.title)) is not None and chapter[1] == 1
    }
    if not chaptered:
        return pictures
    for picture in pictures:
        if picture.part is None:
            continue
        for release in picture.releases:
            chapter = _chapter_of(release.title)
            if chapter is not None and chapter[0] in chaptered and (chapter[1] == picture.part):
                picture.part = None
                break
    return pictures


__all__ = ["_unchaptered"]
