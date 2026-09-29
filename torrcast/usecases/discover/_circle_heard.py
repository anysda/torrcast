"""What the clients of one circle say about the catalogue: whole, heard, and who fell out.

*Whole* is what the screen reads: every indexer answered, and Prowlarr took nobody away,
so an empty circle is the truth about the catalogue. *Heard* is what the memory reads: every
indexer the circle asked answered, so its tiles are what the catalogue holds right now.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient

#: Names that kept silent, names Prowlarr took away, names that refused behind an empty page.
Gone = tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]


def _whole(client: IndexerClient) -> bool:
    """A client that cannot tell (a circle from disk, a fake) proved nothing."""
    whole = getattr(client, "whole", None)
    return bool(whole()) if callable(whole) else False


def _heard(client: IndexerClient) -> bool:
    """A client that cannot tell who it asked is heard only when it is whole."""
    heard = getattr(client, "heard", None)
    return bool(heard()) if callable(heard) else _whole(client)


def _gone(clients: list[IndexerClient]) -> Gone:
    """Who fell out of the circle, over the clients that can tell."""
    silent: set[str] = set()
    banned: set[str] = set()
    refused: set[str] = set()
    for client in clients:
        if callable(gone := getattr(client, "gone", None)):
            quiet, taken, refusing = gone()
            silent.update(quiet)
            banned.update(taken)
            refused.update(refusing)
    refused -= banned
    return tuple(sorted(silent - banned - refused)), tuple(sorted(banned)), tuple(sorted(refused))


__all__ = ["Gone", "_gone", "_heard", "_whole"]
