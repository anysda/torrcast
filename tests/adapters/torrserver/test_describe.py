"""Описатель: .torrent подаётся службе только верный и только раздаче без описания."""

from pathlib import Path

import pytest

from tests.fakes.journal import Tape
from tests.fakes.torrent_file import torrent
from torrcast.adapters.prowlarr.torrent_links import LINKS
from torrcast.adapters.torrserver.describe import describe
from torrcast.adapters.torrserver.describer import DESCRIBER
from torrcast.adapters.torrserver.torrent_store import STORE
from torrcast.ports.journal import slot

KEY, DATA = torrent()
LINK = "http://prowlarr.invalid/1/download?link=x"


class _Service:
    """Служба раздач и Prowlarr в одном: что отдано по ссылке, какой stat, что подано."""

    def __init__(self, stat: int | None = 1, data: bytes | None = DATA) -> None:
        self.state = stat
        self.data = data
        self.fetched: list[str] = []
        self.uploaded: list[tuple[str, bytes]] = []

    def fetch(self, url: str) -> bytes | None:
        self.fetched.append(url)
        return self.data

    def stat(self, key: str) -> int | None:
        return self.state

    def upload(self, key: str, data: bytes) -> bool:
        self.uploaded.append((key, data))
        return True

    def run(self) -> str:
        return describe(
            KEY,
            fetch=self.fetch,
            stat=self.stat,
            upload=self.upload,
            dropped=DESCRIBER.dropped,
        )


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))


def _linked() -> None:
    LINKS.remember([{"infoHash": KEY.upper(), "downloadUrl": LINK}])


@pytest.mark.parametrize("stat", [0, 1])
def test_a_matching_torrent_reaches_a_torrent_still_without_its_description(stat: int) -> None:
    _linked()
    service = _Service(stat=stat)

    assert service.run() == "uploaded"
    assert service.fetched == [LINK]
    assert service.uploaded == [(KEY, DATA)]
    assert STORE.stored(KEY) == DATA


@pytest.mark.parametrize("stat", [2, 3, 4, 5])
def test_a_torrent_that_already_has_a_description_is_never_fed_again(stat: int) -> None:
    # Повторный SetInfoBytes пересобирает куски уже играющей раздачи.
    _linked()
    service = _Service(stat=stat)

    assert service.run() == "swarm-first"
    assert service.uploaded == []
    assert STORE.stored(KEY) == DATA  # закладке после перезапуска пригодится


@pytest.mark.parametrize("answer", [None], ids=["refused, redirected or timed out"])
def test_no_torrent_by_the_link_leaves_the_magnet_alone(answer: bytes | None) -> None:
    _linked()
    service = _Service(data=answer)

    assert service.run() == "no-torrent"
    assert service.uploaded == []
    assert not STORE.has(KEY)


def test_a_torrent_of_another_release_is_refused_and_not_kept() -> None:
    _linked()
    _other_key, other = torrent(name="Up.2009.mkv")
    service = _Service(data=other)

    assert service.run() == "hash-mismatch"
    assert service.uploaded == []
    assert not STORE.has(KEY)


def test_a_torrent_this_process_dropped_is_not_brought_back() -> None:
    _linked()
    DESCRIBER.closed(KEY)
    service = _Service()

    assert service.run() == "dropped"
    assert service.uploaded == []


def test_a_torrent_gone_from_the_service_is_not_brought_back() -> None:
    _linked()
    service = _Service(stat=None)

    assert service.run() == "gone"
    assert service.uploaded == []


def test_a_bookmark_after_a_restart_gets_its_description_from_disk_without_a_link() -> None:
    STORE.store(KEY, DATA)
    service = _Service()

    assert service.run() == "uploaded"
    assert service.fetched == []
    assert service.uploaded == [(KEY, DATA)]


def test_the_outcome_and_its_source_land_in_the_journal(monkeypatch: pytest.MonkeyPatch) -> None:
    tape = Tape()
    slot.install(tape)
    _linked()

    _Service().run()

    (fields,) = tape.named("описание")
    assert (fields["source"], fields["outcome"], fields["hash"]) == ("link", "uploaded", KEY)
    assert "download" not in str(fields)  # ссылка с ключом Prowlarr в журнал не идёт
