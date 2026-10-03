"""Описания на диске: рядом с состоянием, по хэшу, не больше 200 штук."""

import os
from pathlib import Path

import pytest

from torrcast.adapters.torrserver.torrent_store import STORE


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))


def test_a_stored_torrent_lies_next_to_the_state_and_comes_back(tmp_path: Path) -> None:
    key = "ab" * 20
    STORE.store(key.upper(), b"d4:infod1:ai1eee")

    assert (tmp_path / "torrents" / f"{key}.torrent").read_bytes() == b"d4:infod1:ai1eee"
    assert STORE.has(key)
    assert STORE.stored(key) == b"d4:infod1:ai1eee"


def test_an_unknown_torrent_is_not_on_disk() -> None:
    assert not STORE.has("cd" * 20)
    assert STORE.stored("cd" * 20) is None


@pytest.mark.parametrize("key", ["../../etc/passwd", "ab" * 19, "zz" * 20, ""])
def test_a_key_that_is_not_a_hash_never_becomes_a_path(key: str, tmp_path: Path) -> None:
    STORE.store(key, b"d1:ai1ee")

    assert not STORE.has(key)
    assert not (tmp_path / "torrents").exists()


def test_the_store_keeps_the_200_most_recently_used(tmp_path: Path) -> None:
    folder = tmp_path / "torrents"
    keys = [f"{i:040x}" for i in range(201)]
    for age, key in enumerate(keys):
        STORE.store(key, b"d1:ai1ee")
        os.utime(folder / f"{key}.torrent", (1000 + age, 1000 + age))
    STORE.stored(keys[1])  # прочитанное свежеет
    STORE.store("f" * 40, b"d1:ai1ee")

    names = {p.stem for p in folder.glob("*.torrent")}
    assert len(names) == 200
    assert keys[0] not in names and keys[2] not in names
    assert keys[1] in names and "f" * 40 in names
