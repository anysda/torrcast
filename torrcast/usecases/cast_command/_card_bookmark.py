"""The card's bookmark answers before the search circle: its release is already recorded.

Called by the play command (:func:`torrcast.usecases.cast_command._cmd_play._cmd_play`)
right before the circle, and only for a start named by a card key.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

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
    the start to the circle as before: no record (an old bookmark under another key among
    them), no release in it, a finished film, or a recorded release that no longer plays,
    which :func:`_continue` buries out loud, so the circle and the bookmark after it skip it.
    """
    own = args.pinned or args.menu or args.pick is not None or args.episode is not None
    if not args.picture or own:
        return None
    started = state.get(args.picture)
    if started is None or not started.magnet or args.buried(started.magnet):
        return None
    title = spoken_title(started.title, started.original or args.picture_original)
    if started.serial and not args.from_start:
        return _picked_serial(config, state, args.picture, title, None, args=args, clock=clock)
    shown = replace(started, title=title)
    if args.from_start:
        return _from_start(config, args.picture, shown, args=args, clock=clock)
    if not started.resumable:
        return None
    return _continue(config, args.picture, shown, args=args, clock=clock)


__all__ = ["_card_bookmark"]
