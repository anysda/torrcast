"""Тип манифеста и подсказки формата: без них приёмник отвечает LOAD ERROR."""

from __future__ import annotations

from torrcast.adapters.chromecast.cast.hls_hints import HLS_HINTS, HLS_TYPE


def test_the_manifest_is_announced_as_hls_and_not_as_a_bare_file() -> None:
    """Тип манифеста - тот, по которому приёмник понимает, что это HLS."""
    assert HLS_TYPE == "application/vnd.apple.mpegurl"


def test_the_segment_format_is_spelled_out_for_the_default_media_receiver() -> None:
    """Обе подсказки обязательны: без них Default Media Receiver отвечает LOAD ERROR.

    Известная особенность того же Samsung Q70D на муксованном TS - и первый LOAD
    показа встаёт ровно на ней.
    """
    assert HLS_HINTS == {"hlsVideoSegmentFormat": "mpeg2_ts", "hlsSegmentFormat": "ts"}
