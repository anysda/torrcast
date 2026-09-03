"""Запрос на следующую серию: как его назвал бы человек, а не решение, играть её.

Серию называет тот же :meth:`torrcast.domain.entry.Entry.advance`, которым её называет
сторож показа; решение «стоит ли играть» остаётся у :meth:`hass.bridge.Bridge.next`.
"""

from __future__ import annotations

from torrcast.domain.slugify import slugify
from torrcast.ports.playback_session import PlaybackSession
from torrcast.ports.state_store.slot import store


def following(session: PlaybackSession) -> str | None:
    """Запрос на следующую серию; ``None`` - фильм, последняя серия или тишина."""
    if not session.active():
        return None
    entry = store().load().get(session.key())
    if entry is None:
        return None
    after = entry.advance()
    if after.done or not after.label:
        return None
    # Запрос собирается из записи ровно так же, как его собирает поиск следующего
    # сезона (:func:`torrcast.usecases.next_season._next_season`), а серия встаёт в
    # него так же, как её называет человек: `cast киберпанк s2e5` (TC-807).
    words = (entry.query or slugify(entry.title)).replace("-", " ")
    return f"{words} {after.label}"
