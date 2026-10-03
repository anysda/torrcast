"""Infohash описания считается по сырым байтам ``info``, мусор хэша не даёт."""

import hashlib

import pytest

from tests.fakes.torrent_file import bencode, torrent
from torrcast.adapters.torrserver.info_hash import info_hash


def test_the_info_hash_of_a_torrent_is_the_sha1_of_its_info_dictionary() -> None:
    key, data = torrent()

    assert info_hash(data) == key
    assert len(key) == 40


def test_the_hash_is_taken_from_the_raw_bytes_not_from_a_resorted_copy() -> None:
    # Ключи info не по порядку: пересборка дала бы другой хэш, служба считает по байтам.
    raw_info = b"d4:name3:abc6:lengthi5ee"
    data = b"d4:info" + raw_info + b"e"

    assert info_hash(data) == hashlib.sha1(raw_info).hexdigest()


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"magnet:?xt=urn:btih:" + b"a" * 40,
        b"<html>429 Too Many Requests</html>",
        bencode({"announce": "x"}),
        bencode({"info": "not a dictionary"}),
        b"d4:infod4:name3:ab",
        b"d4:infod4:name-3:abcee",
        b"d4:infod6:lengthi5",
    ],
)
def test_anything_but_a_whole_torrent_has_no_info_hash(data: bytes) -> None:
    assert info_hash(data) is None
