"""Английские надписи кластера живой раздачи."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера живой раздачи."""
    return {
        "feed.weight_mb": " ({mb} MB)",
        "feed.shrinking": (
            "v{slot} heavier than the cap{weight} - shrinking in place down to {mbit} Mbit/s"
        ),
        "feed.shrink_reason_none": "nothing to shrink with",
        "feed.shrink_reason_forbidden": "cannot shrink",
        "feed.shrink_reason_failed": "shrink did not work out",
        "feed.shrink_done_reason": "in-place shrink finished",
        "feed.skip_heavy": (
            "⚠️ v{slot} skipping: piece heavier than the cap{weight}, and {reason} - "
            "this place will not be in the show"
        ),
        "feed.source_mute_reason": "the source has been silent for over {secs} s",
        "feed.source_unreadable": (
            "the source will not read ({why}) - falling back to warmed, "
            "waiting for the network to return"
        ),
        "feed.input_torn": "the input broke off midway, the movie is not over",
        "feed.pack_broke_off": "the pack broke off ({why})",
        "feed.retrying": "{what} - starting over, attempt {attempt}",
        "feed.restart_reason": "restart from segment {slot}",
        "feed.pack_from": "packing from {start} s",
        "feed.catchup": " (catch-up {drop} s)",
        "feed.warm_torn": (
            "warmed v{slot} is cut short (missing {missing} s) - redoing with a live pack"
        ),
        "feed.warm_off_grid": (
            "warmed v{slot} is off the grid ({diff} s) - redoing with a live pack"
        ),
        "feed.give_up": (
            "⚠️ v{slot} skipping: {circles} repacks in a row did not deliver this "
            "piece - this place will not be in the show"
        ),
        "feed.pending_too_big": (
            "undelivered pieces are {mb} MB in memory - stopping the pack, "
            "will raise it on the receiver's request"
        ),
        "feed.pending_reason": "{mb} MB undelivered in memory",
        "feed.rest_warmed_reason": "the whole rest is warmed",
        "feed.show_over": "the show is over",
    }
