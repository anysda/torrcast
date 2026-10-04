"""Провод описателя: срок и редирект добычи, ``list`` вместо ``get``, upload без ``save``."""

from typing import Any

import pytest
import requests

from tests.fakes.torrent_file import torrent
from torrcast.adapters.torrserver.describe import BARE
from torrcast.adapters.torrserver.torrent_http import HAS_INFO, TorrentHttp

KEY, DATA = torrent()


class _Raw:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, size: int, decode_content: bool = False) -> bytes:
        assert decode_content, "сжатое тело читается раскрытым, иначе .torrent не узнать"
        return self.body[:size]


class _Response:
    def __init__(self, status: int = 200, body: bytes = b"", payload: Any = None) -> None:
        self.status_code = status
        self.raw = _Raw(body)
        self.payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self) -> Any:
        return self.payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _get(response: _Response | Exception, seen: list[dict[str, Any]]) -> Any:
    def get(url: str, **kwargs: Any) -> _Response:
        seen.append({"url": url, **kwargs})
        if isinstance(response, Exception):
            raise response
        return response

    return get


def test_a_torrent_is_fetched_within_ten_seconds_without_following_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(requests, "get", _get(_Response(body=DATA), seen))

    assert TorrentHttp("http://ts").fetch("http://prowlarr.invalid/1/download") == DATA
    assert seen[0]["timeout"] == 10.0
    assert seen[0]["allow_redirects"] is False


@pytest.mark.parametrize(
    "answer",
    [
        _Response(status=302, body=b""),
        _Response(status=429, body=b"slow down"),
        _Response(status=200, body=b"magnet:?xt=urn:btih:" + KEY.encode()),
        _Response(status=200, body=b"d" + b"x" * (8 * 1024 * 1024)),
        requests.Timeout("read timed out"),
        requests.ConnectionError("refused"),
    ],
    ids=["redirect to magnet", "refusal", "magnet body", "over 8 MiB", "timeout", "no route"],
)
def test_anything_but_a_torrent_by_the_link_is_no_torrent(
    answer: _Response | Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(requests, "get", _get(answer, []))

    assert TorrentHttp("http://ts").fetch("http://prowlarr.invalid/1/download") is None


def test_the_state_is_read_from_the_list_which_never_wakes_a_closed_torrent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[Any] = []

    def post(url: str, **kwargs: Any) -> _Response:
        sent.append((url, kwargs.get("json"), kwargs.get("timeout")))
        return _Response(payload=[{"hash": "00" * 20, "stat": 3}, {"hash": KEY.upper(), "stat": 1}])

    monkeypatch.setattr(requests, "post", post)

    assert TorrentHttp("http://ts/").stat(KEY) == 1
    assert TorrentHttp("http://ts/").stat("ff" * 20) is None
    assert sent[0] == ("http://ts/torrents", {"action": "list"}, 5.0)


@pytest.mark.parametrize(
    "item",
    [
        {"stat": 1, "torrent_size": 734003200, "file_stats": [{"id": 1}]},  # GotInfo потока
        {"stat": 0, "file_stats": [{"id": 1}]},  # повторный add, клиент ещё держит описание
    ],
)
def test_a_torrent_that_already_has_its_description_never_reads_as_bare(
    monkeypatch: pytest.MonkeyPatch, item: dict[str, Any]
) -> None:
    listed = _Response(payload=[{"hash": KEY, **item}])
    monkeypatch.setattr(requests, "post", lambda url, **kw: listed)

    state = TorrentHttp("http://ts").stat(KEY)

    assert state == HAS_INFO
    assert state not in BARE


def test_a_size_from_the_service_database_alone_still_reads_as_bare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listed = _Response(payload=[{"hash": KEY, "stat": 1, "torrent_size": 734003200}])
    monkeypatch.setattr(requests, "post", lambda url, **kw: listed)

    assert TorrentHttp("http://ts").stat(KEY) == 1


def test_an_unreachable_service_reads_as_gone(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(url: str, **kwargs: Any) -> _Response:
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "post", post)

    assert TorrentHttp("http://ts/").stat(KEY) is None
    assert TorrentHttp("http://ts").upload(KEY, DATA) is False


def test_the_upload_carries_the_file_and_no_save_field(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[dict[str, Any]] = []

    def post(url: str, **kwargs: Any) -> _Response:
        sent.append({"url": url, **kwargs})
        return _Response()

    monkeypatch.setattr(requests, "post", post)

    assert TorrentHttp("http://ts").upload(KEY, DATA) is True
    (call,) = sent
    assert call["url"] == "http://ts/torrent/upload"
    assert call["files"]["file"][1] == DATA
    assert "data" not in call  # без поля save служба описание в базу не пишет
