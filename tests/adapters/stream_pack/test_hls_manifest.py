"""Манифест VOD: весь фильм разом, длины кусков и обещание самостоятельных сегментов."""

from __future__ import annotations

import pytest

from torrcast.adapters.stream_pack.hls_manifest import hls_manifest


def test_the_manifest_describes_the_whole_film_and_says_it_has_ended() -> None:
    """У скользящего live-плейлиста длительности нет вовсе, и ТВ считал показ эфиром."""
    spans = [8.0, 8.0, 8.0, 4.0]

    text = hls_manifest(spans, 8, False)

    lines = text.splitlines()
    assert lines[0] == "#EXTM3U"
    assert "#EXT-X-PLAYLIST-TYPE:VOD" in lines and "#EXT-X-TARGETDURATION:8" in lines
    assert lines[-1] == "#EXT-X-ENDLIST" and text.endswith("\n")
    assert "#EXT-X-INDEPENDENT-SEGMENTS" not in lines, "ровная сетка сама себя не обещает"
    written = [
        float(line[len("#EXTINF:") :].rstrip(",")) for line in lines if line[:8] == "#EXTINF:"
    ]
    assert written == spans and sum(written) == pytest.approx(28.0)
    assert [line for line in lines if line.endswith(".ts")] == [f"v{k}.ts" for k in range(4)]


def test_segments_on_keyframes_are_promised_to_be_independent() -> None:
    """Не украшение: приёмнику разрешено начать показ с любого куска - на этом перемотка."""
    assert "#EXT-X-INDEPENDENT-SEGMENTS" in hls_manifest([9.0, 12.0], 12, True)
