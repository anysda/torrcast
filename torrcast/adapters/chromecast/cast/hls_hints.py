"""Тип манифеста и подсказки формата сегментов, с которыми уходит LOAD.

Ставит их в каждую загрузку разговор с приёмником, и больше никто."""

from __future__ import annotations

from torrcast.domain.segment_container import FMP4, MPEGTS, SegmentContainer

#: Тип манифеста и подсказки формата сегментов: без них Default Media Receiver
#: отвечает LOAD ERROR на муксованный TS (известная особенность этого же Q70D).
HLS_TYPE = "application/vnd.apple.mpegurl"
HLS_HINTS = {"hlsVideoSegmentFormat": "mpeg2_ts", "hlsSegmentFormat": "ts"}


def hls_hints(container: SegmentContainer = MPEGTS) -> dict[str, str]:
    """Подсказки LOAD ровно для контейнера текущего показа."""
    if container == FMP4:
        return {
            "hlsSegmentFormat": "fmp4",
            "hlsVideoSegmentFormat": "fmp4",
            "hlsAudioSegmentFormat": "fmp4",
        }
    return dict(HLS_HINTS)
