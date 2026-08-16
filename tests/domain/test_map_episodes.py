"""Tests for mapping torrent files to series episodes."""

from dataclasses import dataclass

from torrcast.domain.map_episodes import map_episodes


@dataclass(frozen=True)
class _File:
    index: int
    name: str
    size: int


def test_files_are_mapped_and_junk_is_ignored() -> None:
    found = map_episodes(
        [
            _File(0, "Show.S01E01.mkv", 100),
            _File(1, "Show.S01E02.mkv", 100),
            _File(2, "sample.S01E03.mkv", 1),
        ]
    )
    assert [(item.season, item.episode) for item in found] == [(1, 1), (1, 2)]
