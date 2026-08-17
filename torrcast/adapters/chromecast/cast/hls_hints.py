"""Тип манифеста и подсказки формата сегментов, с которыми уходит LOAD.

Ставит их в каждую загрузку разговор с приёмником, и больше никто."""

from __future__ import annotations

#: Тип манифеста и подсказки формата сегментов: без них Default Media Receiver
#: отвечает LOAD ERROR на муксованный TS (известная особенность этого же Q70D).
HLS_TYPE = "application/vnd.apple.mpegurl"
HLS_HINTS = {"hlsVideoSegmentFormat": "mpeg2_ts", "hlsSegmentFormat": "ts"}
