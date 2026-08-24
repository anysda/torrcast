"""CMAF master playlist naming the exact codec family and media playlist."""


def master_manifest(video_codec: str) -> str:
    """Build the single-variant master used by the fMP4 delivery path."""
    codecs = f"{video_codec},mp4a.40.2"
    return "\n".join(
        (
            "#EXTM3U",
            "#EXT-X-VERSION:7",
            f'#EXT-X-STREAM-INF:BANDWIDTH=50000000,CODECS="{codecs}"',
            "stream.m3u8",
            "",
        )
    )
