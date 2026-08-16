"""Зеркально проверяет разбор магнита и уборку своих раздач."""

from torrcast.usecases.torrents import (
    _held_by_show,
    _own_torrent,
    _release_orphans,
    _release_torrents,
    _torrent_hash,
)

HASH = "4f2c1a90bd9e3f1fbaa1a8b8b7c0d1e2f3a4b5c6"


def test_hash_comes_from_the_magnet_itself() -> None:
    assert _torrent_hash(f"magnet:?xt=urn:btih:{HASH.upper()}&dn=x") == HASH
    assert _torrent_hash("magnet:?xt=urn:btih:MFRGGZDFMZTWQ2LKNNWG23TP") == ""
    assert _torrent_hash("") == ""


def test_housekeeping_units_are_callable() -> None:
    assert all(
        callable(unit)
        for unit in (_release_torrents, _own_torrent, _release_orphans, _held_by_show)
    )
