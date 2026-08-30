"""Английский каталог кластера предстартовых заметок."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера предстартовых заметок."""
    return {
        "notes.bitrate_warn_recode": (
            "attention: ~{mbit} Mbit/s - heavy chunks get recoded on the fly"
        ),
        "notes.bitrate_warn_no_recode": (
            "attention: ~{mbit} Mbit/s - the receiver may choke at this bitrate"
        ),
        "notes.file_debug": "file: {base} · {size} · {duration} · {video}",
    }
