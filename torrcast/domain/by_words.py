"""Правило by words; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.group_weight import _group_weight
from torrcast.domain.paired import _paired
from torrcast.domain.picture import Picture
from torrcast.domain.word_list import _word_list
from torrcast.domain.words import _words


def _by_words(wanted: str, groups: dict[str, list[Picture]]) -> str | None:
    asked = _words(wanted)
    if len(asked) < 2:
        return None
    hits = [key for key in groups if asked <= _words(key)]
    if not hits:
        mine = _word_list(wanted)
        hits = [key for key in groups if _paired(mine, _word_list(key))]
    return (
        min(hits, key=lambda key: (len(_words(key)), len(key), -_group_weight(groups, key), key))
        if hits
        else None
    )


__all__ = ["_by_words"]
