"""Правило paired; используют модели и фасады разбора имён."""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.same_word import same_word


def _paired(mine: Sequence[str], theirs: Sequence[str]) -> bool:
    if len(mine) < 2 or len(mine) != len(theirs):
        return False
    left = list(enumerate(theirs))
    for here, word in enumerate(mine):
        pair = next(
            (
                spot
                for spot in left
                if word == spot[1] or (spot[0] != here and same_word(word, spot[1]))
            ),
            None,
        )
        if pair is None:
            return False
        left.remove(pair)
    return True


__all__ = ["_paired"]
