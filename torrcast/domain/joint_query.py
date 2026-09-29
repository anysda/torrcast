"""Several texts in one request, for the indexer that answers them all at once.

Prowlarr paces requests by the host string: a second request to the same host waits two
seconds behind the first, a third four. The picture's names are asked beside the viewer's
text (:class:`~torrcast.usecases.discover.named_round.NamedRound`), so every host used to
get three requests at once, and the last of them could not even start before the fourth
second. Our own JacRed adapter (``scripts/jacred-indexer.py``) takes the names in one
request instead, joined by :data:`JOINT`, asks the API for each in parallel and returns
the rows together: one request, one pause.
"""

from __future__ import annotations

from typing import Final

#: What joins the texts of one request. Spaces around the bar keep it out of
#: :func:`~torrcast.domain.wire_query.wire_query`, which glues a bar between two letters.
JOINT: Final = " | "
#: Indexers that split a joined request themselves: only our own adapter does.
JOINT_INDEXERS: Final = ("jacred",)
#: How far behind the viewer's text the names are asked. The pacing hands out the slots in
#: the order the requests arrive, so texts sent at once drew them at random, and the
#: viewer's text, the only one making tiles, could start four seconds late with a budget of
#: three. Behind it the names leave it the first slot at every host.
NAMES_BEHIND: Final = 0.3


def _joint_indexer(name: str) -> bool:
    """Does this indexer take several texts in one request?"""
    low = name.lower()
    return any(part in low for part in JOINT_INDEXERS)


def joint_query(name: str, query: str, joint: str | None) -> str:
    """What to ask ``name``: ``joint`` if it takes joined texts, ``query`` otherwise.

    ``joint`` is ``None`` for an ordinary circle; an empty one means another circle of the
    same names already carries them for this indexer, and it is not asked here at all.
    """
    return joint if joint is not None and _joint_indexer(name) else query


__all__ = ["JOINT", "JOINT_INDEXERS", "NAMES_BEHIND", "joint_query"]
