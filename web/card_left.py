"""Карточка ушла с экрана: ``POST /api/card-left``.

Карточка держит в TorrServer раздачу, которую сыграл бы показ (:mod:`web.card_warm`), и
держит её ровно пока она на экране. Страница называет ключ картины, с которой ушла;
прогрев чужой картины и раздача, которую уже забрал показ, этим не трогаются.
"""

from __future__ import annotations

from web.answer import Answer
from web.card_warm import CARD_WARM
from web.refusal import refusal
from web.request import Request

#: Длиннее ключ картины не бывает: тот же потолок, что у ключа в ``POST /api/play``.
_KEY_LIMIT = 300


def card_left(request: Request) -> Answer:
    """Снять прогрев раздачи карточки, с которой страница ушла."""
    picture = request.body.get("picture")
    if not isinstance(picture, str) or not picture or len(picture) > _KEY_LIMIT:
        return refusal(400, "bad_picture")
    CARD_WARM.leave(picture)
    return Answer(204, b"")
