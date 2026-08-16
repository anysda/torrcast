"""Tests for the structural torrent-file interface."""

from torrcast.domain.file_like import FileLike


def test_file_like_is_a_protocol() -> None:
    assert FileLike.__name__ == "FileLike"
