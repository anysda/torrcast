"""Seek probes must request and count the container they actually pack."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_probes import probe
from torrcast.adapters.http_server.hls_server import HlsServer
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.domain.segment_container import FMP4, MPEGTS, SegmentContainer


@pytest.mark.parametrize("container,suffix", [(FMP4, ".m4s"), (MPEGTS, ".ts")])
@pytest.mark.parametrize("name", ["seekcheck", "seekbench"])
def test_seek_requests_the_packed_container(
    tmp_path: Path, container: SegmentContainer, suffix: str, name: str
) -> None:
    """A server holding only the selected format exposes a wrong suffix as 404.

    The product's Feed can alias a wrong suffix to the right bytes, hiding this
    mistake while the HTTP content type and the probe's claimed request disagree.
    """
    module = probe(name)
    (tmp_path / f"v0{suffix}").write_bytes(b"packed segment")
    feed = SimpleNamespace(
        container=container,
        grid=Grid.uniform(20.0),
        prune=lambda _: None,
        restart=lambda _: None,
        weight=lambda: 14,
    )
    server = HlsServer(tmp_path, host="127.0.0.1", port=0)
    server.start()
    try:
        assert server._server is not None
        base = f"http://127.0.0.1:{server._server.server_port}"
        if name == "seekcheck":
            consumer = module.Consumer(base, feed, timeout=2.0)
            consumer.take(0)
            assert consumer.misses == 0
        else:
            got = module.leap(feed, base, to=0.0, window=1.0, timeout=2.0)
            assert got["given"] == 1
            assert got["film"] == 10.0
    finally:
        server.stop()


@pytest.mark.parametrize("container,expected", [(FMP4, [2]), (MPEGTS, [1])])
def test_seek_counts_only_segments_in_its_container(
    tmp_path: Path, container: SegmentContainer, expected: list[int]
) -> None:
    """The backward-seek report must see fmp4 pieces still present in tmpfs."""
    for name in ("v1.ts", "v2.m4s", "init.mp4"):
        (tmp_path / name).write_bytes(b"segment")
    assert probe("seekcheck")._slots(SimpleNamespace(out=tmp_path, container=container)) == expected
