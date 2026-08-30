"""English captions of the torrserver cluster."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Return the English catalog of the torrserver cluster."""
    return {
        "torrserver.unexpected_answer_add": "TorrServer returned an unexpected answer to the add",
        "torrserver.no_hash": "TorrServer did not hand back the torrent hash",
        "torrserver.unexpected_answer_files": (
            "TorrServer returned an unexpected answer to the file list"
        ),
        "torrserver.unexpected_answer_cache": (
            "TorrServer returned an unexpected answer to the cache counter"
        ),
        "torrserver.swarm_empty": "swarm is empty - not one peer in {seconds} s",
        "torrserver.metadata_timeout": "torrent gave no metadata in {timeout} s - no peers",
        "torrserver.unexpected_answer_list": (
            "TorrServer returned an unexpected answer to the torrent list"
        ),
        "torrserver.unresponsive": "TorrServer does not answer ({base_url}): {reason}",
        "torrserver.not_json": "TorrServer returned a non-JSON answer",
        "torrserver.warmup_timed_out": "TorrServer did not accept the torrent in time",
    }
