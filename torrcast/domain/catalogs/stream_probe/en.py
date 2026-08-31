"""English captions of the stream_probe cluster."""

from __future__ import annotations


def en() -> dict[str, str]:
    return {
        "stream_probe.disc_image": (
            "the torrent has no separate video file (looks like a disc image) - "
            "take another release: cast <query> --release N"
        ),
        "stream_probe.swarm_silent": "the swarm is silent - not one byte arrived within the grace",
        "stream_probe.service_down": "TorrServer does not answer",
        "stream_probe.torrent_lost": "TorrServer lost our torrent",
        "stream_probe.no_trackers": "the torrent is left without trackers - it has no metadata",
        "stream_probe.thin_swarm": (
            "the swarm delivers {got} Mbit/s against the needed {need} Mbit/s - "
            "supply is short ({ratio}x)"
        ),
    }
