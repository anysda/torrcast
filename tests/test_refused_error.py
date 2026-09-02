"""Зеркало отказа: слово договора доезжает до карточки ровно тем же, каким названо."""

from __future__ import annotations

from hass.bridge import BUSY, NO_NEXT, NO_VOLUME, NOTHING_PLAYING
from hass.refused_error import RefusedError


def test_the_word_of_the_refusal_survives_the_raise() -> None:
    for word in (BUSY, NOTHING_PLAYING, NO_NEXT, NO_VOLUME):
        assert RefusedError(word).word == word


def test_the_words_of_the_contract_do_not_repeat_each_other() -> None:
    words = (BUSY, NOTHING_PLAYING, NO_NEXT, NO_VOLUME)

    assert len(set(words)) == len(words)
