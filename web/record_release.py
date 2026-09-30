"""Отпущенная держателем раздача записи: первая в ряду паркуется, прочая сносится."""

from __future__ import annotations

import contextlib

from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.parking_engine import ParkingEngine
from torrcast.ports.torrent_engine import TorrentEngine


def record_release(engine: TorrentEngine, torrent_hash: str, *, keep: bool) -> None:
    """Отпустить раздачу записи: первую в ряду - с кэшем на диске, прочую - сносом.

    Снос первой стирал кэш, и кусок закладки шёл из роя до 30 с; запаркованные прочие
    копили кэш навсегда.
    """
    with contextlib.suppress(TorrcastError):
        if keep and isinstance(engine, ParkingEngine):
            engine.park(torrent_hash)
        else:
            engine.drop(torrent_hash)
