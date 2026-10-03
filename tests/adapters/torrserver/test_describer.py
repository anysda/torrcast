"""Описатель процесса: поток только при источнике, снятая раздача вне игры до ``add``."""

from pathlib import Path

import pytest

from tests.fakes.torrent_file import torrent
from torrcast.adapters.prowlarr.torrent_links import LINKS
from torrcast.adapters.torrserver.describer import DESCRIBER
from torrcast.adapters.torrserver.torrent_http import TorrentHttp

KEY, DATA = torrent()
LINK = "http://prowlarr.invalid/1/download?link=x"


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))


def test_without_a_link_or_a_stored_torrent_no_thread_is_started() -> None:
    assert DESCRIBER.later("http://torrserver", KEY) is None


def test_the_description_reaches_the_service_from_its_own_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    LINKS.remember([{"infoHash": KEY.upper(), "downloadUrl": LINK}])
    uploaded: list[tuple[str, bytes]] = []

    def upload(_http: TorrentHttp, key: str, data: bytes) -> bool:
        uploaded.append((key, data))
        return True

    monkeypatch.setattr(TorrentHttp, "fetch", lambda _http, url: DATA if url == LINK else None)
    monkeypatch.setattr(TorrentHttp, "stat", lambda _http, key: 1)
    monkeypatch.setattr(TorrentHttp, "upload", upload)

    thread = DESCRIBER.later("http://torrserver", KEY.upper())
    assert thread is not None
    thread.join(5)

    assert uploaded == [(KEY, DATA)]


def test_a_new_add_after_a_drop_lifts_the_ban() -> None:
    DESCRIBER.closed(KEY)
    assert DESCRIBER.dropped(KEY)

    DESCRIBER.later("http://torrserver", KEY)

    assert not DESCRIBER.dropped(KEY)
