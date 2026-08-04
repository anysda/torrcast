"""Формат потока §3 и https-раздача: то, на чём ресивер молча ломается.

Проверяется ровно то, что зафиксировано ТЗ и реестром ТВ-рисков §9: TS-сегменты по 4 с,
один вариант, видео copy, аудио всегда AAC stereo 192k, EVENT-манифест, CORS на всех
ответах (включая 404 и preflight) и Range на сегментах.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from torrcast.cast import Report, parse_manifest
from torrcast.stream import HlsServer, ffmpeg_hls_command, hls_dir


@pytest.fixture
def served(tls: tuple[str, str], tmp_path: Path) -> Any:
    """Живой https-сервер с одним сегментом и манифестом."""
    root = hls_dir(str(tmp_path / "hls"))
    (root / "index0.ts").write_bytes(bytes(range(256)) * 4)
    (root / "index.m3u8").write_text("#EXTM3U\n#EXTINF:4.000000,\nindex0.ts\n")
    server = HlsServer(root, tls[0], tls[1], host="127.0.0.1", port=18453)
    server.start()
    session = requests.Session()
    session.verify = tls[0]  # серт = собственный корень: TLS проверяется по-настоящему
    try:
        yield session, "https://127.0.0.1:18453"
    finally:
        server.stop()


def test_stream_format_is_the_one_fixed_by_the_spec() -> None:
    command = ffmpeg_hls_command("http://ts/stream", audio_index=1, out_dir="/dev/shm/torrcast")
    text = " ".join(command)
    assert "-c:v copy" in text, "видео только copy — перекодировать 1080p нам нечем"
    assert "-c:a aac -ac 2 -b:a 192k" in text, "AC3/DTS passthrough запрещён (§3)"
    assert "-map 0:v:0 -map 0:a:1" in text, "один вариант и выбранная дорожка по индексу"
    assert "-hls_time 4" in text and "-hls_segment_type mpegts" in text
    assert "-hls_playlist_type event" in text, "иначе приёмник стартует с середины фильма"
    assert command[-1].endswith("/index.m3u8")


def test_seek_is_an_input_option_before_the_source() -> None:
    """Перемотка и resume — рестарт с ``-ss`` на входе (§3, понадобится этапу 3)."""
    command = ffmpeg_hls_command("http://ts/stream", 0, "/tmp/x", start_pos=1207.5)
    assert command[command.index("-ss") + 1] == "1207.500"
    assert command.index("-ss") < command.index("-i")
    assert "-ss" not in ffmpeg_hls_command("http://ts/stream", 0, "/tmp/x")


def test_readrate_paces_packing_and_can_be_switched_off() -> None:
    assert "-readrate" in ffmpeg_hls_command("u", 0, "/tmp/x", readrate=1.0)
    assert "-readrate" not in ffmpeg_hls_command("u", 0, "/tmp/x", readrate=0.0)


def test_cors_is_on_every_answer_including_404_and_preflight(served: Any) -> None:
    """Chromecast без ``Access-Control-Allow-Origin`` молча не играет (§9)."""
    session, base = served
    for method, path in (("get", "/index.m3u8"), ("head", "/index0.ts"), ("get", "/нет.ts")):
        response = getattr(session, method)(f"{base}{path}", timeout=10)
        assert response.headers.get("Access-Control-Allow-Origin") == "*", path
    options = session.options(f"{base}/index.m3u8", timeout=10)
    assert options.headers.get("Access-Control-Allow-Origin") == "*"


def test_content_types_are_what_the_receiver_expects(served: Any) -> None:
    session, base = served
    assert session.get(f"{base}/index.m3u8").headers["Content-Type"] == (
        "application/vnd.apple.mpegurl"
    )
    assert session.get(f"{base}/index0.ts").headers["Content-Type"] == "video/mp2t"


def test_segments_answer_range_requests(served: Any) -> None:
    """Q70D переспрашивает куски диапазонами — без 206 он встаёт (грабли kinocast)."""
    session, base = served
    response = session.get(f"{base}/index0.ts", headers={"Range": "bytes=10-19"}, timeout=10)
    assert response.status_code == 206
    assert response.headers["Content-Range"] == "bytes 10-19/1024"
    assert len(response.content) == 10
    tail = session.get(f"{base}/index0.ts", headers={"Range": "bytes=-16"}, timeout=10)
    assert tail.status_code == 206 and len(tail.content) == 16
    bad = session.get(f"{base}/index0.ts", headers={"Range": "bytes=5000-6000"}, timeout=10)
    assert bad.status_code == 416


def test_nothing_but_the_stream_is_reachable(served: Any) -> None:
    """Наружу открыт не каталог, а ровно манифест и сегменты."""
    session, base = served
    for path in ("/", "/../../etc/passwd", "/index.m3u8.tmp", "/config.json"):
        assert session.get(f"{base}{path}", timeout=10).status_code == 404, path


def test_manifest_is_parsed_into_segments_and_the_end_marker() -> None:
    text = "#EXTM3U\n#EXTINF:4.000000,\nindex0.ts\n#EXTINF:2.500000,\nindex1.ts\n#EXT-X-ENDLIST\n"
    segments, ended = parse_manifest(text)
    assert segments == [("index0.ts", 4.0), ("index1.ts", 2.5)]
    assert ended
    assert parse_manifest("#EXTM3U\n")[1] is False


def test_acceptance_verdict_needs_no_gaps_no_missing_cors_and_a_full_decode() -> None:
    full = Report(segments=1800, duration=7200.0, decoded=7199.0)
    assert full.ok
    assert not Report(segments=1800, duration=7200.0, decoded=7199.0, gaps=1).ok
    assert not Report(segments=1800, duration=7200.0, decoded=7199.0, no_cors=1).ok
    assert not Report(segments=1800, duration=7200.0, decoded=3000.0).ok, "оборвался посередине"
    assert not Report().ok, "приёмник вообще ничего не увидел"
