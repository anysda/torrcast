"""Проверяет разбор заранее полученного JSON ffprobe."""

import json

from torrcast.adapters.ffprobe.parse_media import parse_media


def test_parses_tracks_picture_and_tagged_bitrate() -> None:
    text = json.dumps(
        {
            "format": {"duration": "120.5"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "hevc",
                    "width": 1920,
                    "height": 800,
                    "tags": {"BPS-eng": "14000000"},
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "channels": 6,
                    "tags": {"language": "rus", "title": "Дубляж"},
                },
            ],
        }
    )
    media = parse_media(text)
    assert (media.duration, media.video, media.width, media.video_bps) == (
        120.5,
        "hevc",
        1920,
        14_000_000.0,
    )
    assert (media.tracks[0].language, media.tracks[0].title) == ("rus", "Дубляж")
