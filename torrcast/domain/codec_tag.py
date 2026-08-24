"""RFC 6381 codec tags used by the CMAF master playlist."""


def codec_tag(codec: str, depth: int = 8) -> str:
    """Name the video sample entry delivered by the copy path."""
    if codec == "hevc":
        return "hvc1.2.4.L120.B0" if depth > 8 else "hvc1.1.6.L120.B0"
    if codec == "vp9":
        return f"vp09.00.41.{depth:02d}"
    return "avc1.640028"
