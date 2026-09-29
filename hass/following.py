"""Запрос на следующую серию: как его назвал бы человек, а не решение, играть её.

Серию называет тот же :meth:`torrcast.domain.entry.Entry.advance`, которым её называет
сторож показа; решение «стоит ли играть» остаётся у :meth:`hass.bridge.Bridge.next`.
"""

from __future__ import annotations

from hass.catalog_next import catalog_next, catalog_waits
from torrcast.domain.entry import Entry
from torrcast.domain.slugify import slugify
from torrcast.ports.playback_session import PlaybackSession
from torrcast.ports.state_store.slot import store


def following(session: PlaybackSession) -> str | None:
    """Запрос на следующую серию; ``None`` - фильм, последняя серия сериала или тишина."""
    entry = _entry(session)
    if entry is None:
        return None
    after = entry.advance()
    # Запрос собирается из записи ровно так же, как его собирает поиск следующего
    # сезона (:func:`torrcast.usecases.next_season._next_season`), а серия встаёт в
    # него так же, как её называет человек: `cast киберпанк s2e5` (TC-807).
    words = (entry.query or slugify(entry.title)).replace("-", " ")
    # Раздача кончилась - сериал не обязательно: серию за её краем называет каталог.
    label = catalog_next(entry, session.key(), words) if after.done else after.label
    return f"{words} {label}" if label else None


def waits_for_next(session: PlaybackSession) -> bool:
    """Стык без ответа TVmaze держит вкладку до единственного поиска юнита."""
    entry = _entry(session)
    return bool(entry is not None and entry.advance().done and catalog_waits(entry))


def _entry(session: PlaybackSession) -> Entry | None:
    if not session.active():
        return None
    return store().load().get(session.key())
