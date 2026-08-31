"""Английский каталог кластера прогрева."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера прогрева."""
    return {
        "warm.progress_head": "warmed {warmed} of {duration}",
        "warm.done_note": "{head} - the whole picture is on disk, no internet needed anymore",
        "warm.next_note": "{done}; next: {next}",
        "warm.trouble_note": "{head} - warming stalled: {trouble}",
        "warm.warming_on": "{head} - still warming",
        "warm.busy_rival": "yielded to live recode",
        "warm.waiting_slot": "waiting for playback headroom",
        "warm.warming_why": "{head} - still warming ({why})",
        "warm.budget_exhausted": "disk budget of {budget} GB is used up",
        "warm.floor_reached": "the partition has {free} GB free - that's the last reserve",
        "warm.fit": "fits",
        "warm.skew": "off grid",
        "warm.blind": "unchecked",
        "warm.skew_where": "v{slot} landed off the grid at minute {minute} ({diff} s)",
        "warm.skew_hole": "{where} - this spot is left unwarmed",
        "warm.skew_retry": "{where} - relaying it again",
        "warm.blind_why_timecode": "timecode unreadable",
        "warm.blind_why_not_movie": "run tape, not the picture",
        "warm.blind_note": (
            "nothing to check the warming grid against ({why}) - the layout guard is blind here"
        ),
    }
