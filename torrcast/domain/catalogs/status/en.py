"""Английские надписи кластера ``cast status``."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера ``cast status``."""
    return {
        "status.warmed": "   warmed {warm} of {duration}",
        "status.warmed_whole": " - the whole movie is on disk, no internet needed",
        "status.file_info": (
            "   {ident} · file #{file} · track {track} · stream {addr}, receiver {receiver}"
        ),
        "status.no_frame": "there was not a single frame",
        "status.at": "at {pos}",
        "status.torn": "the show broke off: {what} - {was} ({reason})",
        "status.nothing_playing": "nothing is playing",
        "status.last_resumable": "last: “{title}” at {pos} / {duration}",
        "status.playing": "playing {what} - {pos} / {duration}",
        "status.dark": "the show went dark: {what} - {pos} / {duration}",
        "status.dark_wait": (
            "   {darkness} ({reason}) - waiting for the return, will raise it myself"
        ),
        "status.darkness_for": "dark for {hms}",
        "status.darkness": "dark",
    }
