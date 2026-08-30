"""Бухгалтерия досмотра: закладка, доехавшая до конца, становится «досмотрено».

Зовут её команда показа (:func:`_cmd_play`) и закладка выбранной картины
(:mod:`torrcast.usecases.cast_command._bookmark`) - каждая на своём раннем выходе.
"""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store.slot import store as watch_store
from torrcast.usecases.rank._hms import _hms


def _account_watched(state: WatchState, found: tuple[str, Entry]) -> tuple[tuple[str, Entry], bool]:
    """На следующем ``cast`` превратить закладку >= 95 % в «досмотрено».

    Это бухгалтерия сохранённого места, не переход играющего сериала: живой юнит
    по-прежнему берёт следующую серию только после естественного конца потока.
    """
    key, entry = found
    if entry.done or not entry.watched:
        return found, False
    stopped, label = entry.pos, entry.label
    following = entry.advance()
    state.put(key, following)
    watch_store().save(state)
    if following.serial and following.done:
        return (key, following), True  # строку и выбор перезапуска ведёт ``_continue``
    what = f" {label}" if label else ""
    decision = (
        phrase("account_watched.next_label", label=following.label)
        if following.serial and not following.done
        else phrase("account_watched.from_start")
    )
    print(
        phrase(
            "account_watched.done",
            title=entry.title,
            what=what,
            stopped=_hms(stopped),
            dur=_hms(entry.dur),
            decision=decision,
        )
    )
    return (key, following), True
