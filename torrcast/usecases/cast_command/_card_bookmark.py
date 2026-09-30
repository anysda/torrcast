"""The card's bookmark answers before the search circle: its release is already recorded.

Called by the play command (:func:`torrcast.usecases.cast_command._cmd_play._cmd_play`)
right before the circle, and only for a start named by a card key.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from torrcast.domain.slugify import slugify
from torrcast.domain.spoken_title import spoken_title
from torrcast.usecases.cast_command._bookmark import _from_start
from torrcast.usecases.cast_command._picked_serial import _picked_serial
from torrcast.usecases.select._continue import _continue

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.config import Config
    from torrcast.domain.watch_state import WatchState
    from torrcast.usecases.start_clock import _Clock


def _card_bookmark(config: Config, state: WatchState, args: Args, *, clock: _Clock) -> int | None:
    """Play the bookmark of the card's picture without asking the indexers first.

    The bookmark is kept under the picture key, and the card names that key: the recorded
    release, file and place answer «Play» on their own. Asking the circle first only to
    find the same key in it cost path A a whole search, and when the indexers were silent
    the start ended ``not_found`` on a picture that had just played (Cars, 2 of 3 on the
    stand, 30-09-2026).

    The branches are those of :func:`torrcast.usecases.cast_command._bookmark._continue_picked`
    that do not need the circle: from the start, a started series, a started film. A named
    release, a menu, a pick number and a named episode still go the usual way. ``None`` sends
    the start to the circle as before: no record under any name of the card's picture
    (:func:`_bookmark_key`), no release in it, a finished film, or a release that no longer plays,
    which :func:`_continue` buries out loud, so the circle and the bookmark after it skip it.
    Nothing buries a release before this call: a card start is a menu start, and the early
    bookmark exits of the play command are closed to it.
    """
    own = args.pinned or args.menu or args.pick is not None or args.episode is not None
    if not args.picture or own:
        return None
    key = _bookmark_key(state, args.picture)
    started = None if key is None else state.get(key)
    if key is None or started is None or not started.magnet:
        return None
    title = spoken_title(started.title, started.original or args.picture_original)
    if started.serial and not args.from_start:
        return _picked_serial(config, state, key, title, None, args=args, clock=clock)
    shown = replace(started, title=title)
    if args.from_start:
        return _from_start(config, key, shown, args=args, clock=clock)
    if not started.resumable:
        return None
    return _continue(config, key, shown, args=args, clock=clock)


def _bookmark_key(state: WatchState, card: str) -> str | None:
    """The key the card's picture is bookmarked under: its own, or the one of its other name.

    The circle names one picture by either of its names, so the card and the bookmark can
    hold different keys: the card opened from the search as ``movie:cars:2006`` while the
    bookmark lay under ``movie:тачки:2006`` (stand, 30-09-2026). Missed, «Play» went to the
    circle and started the film from zero over the saved place. A bookmark of the same kind
    and year answers when the card's name is its title or original, and only when it is one.

    Without a year only the card's own key answers. The key of such a picture already carries
    its original (:attr:`torrcast.domain.picture.Picture.key`), and one shared name is no proof:
    ``tv:дом:0`` is not ``tv:дом-house:0``, and the wrong one would start from its place.
    """
    if state.get(card) is not None:
        return card
    kind, _, rest = card.partition(":")
    name, _, year = rest.rpartition(":")
    if year == "0":
        return None
    named = [
        key
        for key, entry in state.entries.items()
        if key.partition(":")[0] == kind
        and key.rpartition(":")[2] == year
        and name in {slugify(entry.title), slugify(entry.original or "")}
    ]
    return named[0] if len(named) == 1 else None


__all__ = ["_card_bookmark"]
