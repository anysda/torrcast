"""Хэш раздачи разбирается из самого магнита, и только в hex-форме."""

from torrcast.domain.torrent_hash import _torrent_hash

HASH = "4f2c1a90bd9e3f1fbaa1a8b8b7c0d1e2f3a4b5c6"


def test_hex_form_is_taken_and_lowercased() -> None:
    assert _torrent_hash(f"magnet:?xt=urn:btih:{HASH.upper()}&dn=x") == HASH


def test_base32_and_junk_give_nothing() -> None:
    assert _torrent_hash("magnet:?xt=urn:btih:MFRGGZDFMZTWQ2LKNNWG23TP&dn=x") == ""
    assert _torrent_hash("magnet:?xt=1") == "" and _torrent_hash("") == ""
