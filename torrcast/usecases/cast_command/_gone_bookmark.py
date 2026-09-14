"""An episode row whose bookmark release left the pool: the bookmark still plays first."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.info_hash import info_hash
from torrcast.domain.magnet_hash import magnet_hash

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.entry import Entry
    from torrcast.usecases.select.plan import Plan


def _gone_bookmark(plan: Plan, entry: Entry, args: Args) -> bool:
    """The card row carries the bookmark release, and the pool no longer names it.

    An indexer drops a release while its swarm lives on, and the bookmark outranks the card
    (TC-1263): the show plays the recorded release at the named episode first
    (:func:`torrcast.usecases.select._continue._continue`). A dead one is buried out loud,
    and the usual selection takes the episode from a pooled release, saying so.
    """
    saved = magnet_hash(entry.magnet)
    named = args.episode
    return bool(
        saved
        and entry.serial
        and named is not None
        and args.card_release == saved
        and not args.buried(entry.magnet)
        and entry.where(named.season, named.episode) >= 0
        and all(info_hash(release) != saved for release in plan.picture.releases)
    )


__all__ = ["_gone_bookmark"]
