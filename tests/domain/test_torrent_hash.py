"""Хэш раздачи разбирается из самого магнита: hex как есть, base32 - в тот же hex."""

from torrcast.domain.torrent_hash import _torrent_hash

HASH = "4f2c1a90bd9e3f1fbaa1a8b8b7c0d1e2f3a4b5c6"
#: Те же двадцать байт ``00 01 .. 13`` в двух формах магнита.
BASE32, HEXED = "AAAQEAYEAUDAOCAJBIFQYDIOB4IBCEQT", "000102030405060708090a0b0c0d0e0f10111213"


def test_hex_form_is_taken_and_lowercased() -> None:
    assert _torrent_hash(f"magnet:?xt=urn:btih:{HASH.upper()}&dn=x") == HASH


def test_base32_form_becomes_the_hex_torrserver_lists() -> None:
    """Без перевода запись с base32-магнитом не убиралась, и её кэш лежал в службе вечно."""
    assert _torrent_hash(f"magnet:?xt=urn:btih:{BASE32}&dn=x") == HEXED
    assert _torrent_hash(f"magnet:?xt=urn:btih:{BASE32.lower()}") == HEXED


def test_junk_gives_nothing() -> None:
    assert _torrent_hash("magnet:?xt=urn:btih:MFRGGZDFMZTWQ2LKNNWG23TP&dn=x") == ""
    assert _torrent_hash(f"magnet:?xt=urn:btih:{BASE32}A") == ""
    assert _torrent_hash(f"magnet:?xt=urn:btih:{HASH}0") == ""
    assert _torrent_hash("magnet:?xt=1") == "" and _torrent_hash("") == ""
