"""Английские надписи кластера запаса показа в кэше службы раздач."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера запаса показа в кэше службы раздач."""
    return {
        "cache.by_measurement": "by measurement",
        "cache.by_estimate": "by estimate",
        "cache.reserve_unknown_no_answer": (
            "cache reserve unknown - the torrent service is not answering"
        ),
        "cache.reserve_unknown_silent": (
            "cache reserve unknown - the service is silent about it"
        ),
        "cache.reserve_empty": "the service cache is empty, no reserve for playback",
        "cache.reserve_unconvertible": (
            "there is a cache reserve, cannot convert it to minutes - "
            "the file bitrate is unknown"
        ),
        "cache.reserve_under_minute": "the service cache reserve is under a minute of playback",
        "cache.reserve_minutes": (
            "the service cache holds a reserve for {minutes} more min of playback ({source})"
        ),
    }
