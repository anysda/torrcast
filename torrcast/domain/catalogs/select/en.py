"""Английские надписи кластера отбора."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера отбора."""
    return {
        "select.phase_queue": "queue",
        "select.phase_release": "release",
        "select.phase_tracks": "tracks",
        "select.no_file_chosen": "no release file chosen",
        "select.stream_not_read": "stream not read",
        "select.timing": "metadata {meta}s, tracks {read}s",
        "select.replay_from_start": (
            "“{title}” - {label} was the last one in the release, so playing from the start"
        ),
        "select.buried_place": " from {pos}",
        "select.buried_note": (
            "“{title}”{named} - the recorded release does not play: {why}; "
            "looking for another{place}"
        ),
        "select.file_gone": "file №{index} is no longer in it",
        "select.timed_out": "gave up after {secs}s",
        "select.gave_up": "gave up waiting",
        "select.release_missing_new_listing": (
            "shown release {release} of “{title}” is not in the new listing"
        ),
        "select.release_number_missing": "“{title}” has {total} releases, no number {release}",
        "select.other_menu": "pick another: --menu",
        "select.track_number": "track {number}",
        "select.from_position": "from {pos}",
    }
