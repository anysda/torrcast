"""English captions of the recode cluster."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Return the English catalog of the recode cluster."""
    return {
        "recode.no_heavy_pieces": "no heavy pieces - nothing to recode",
        "recode.and": "and",
        "recode.bitrate_from": "bitrate from {mbit} Mbit/s",
        "recode.piece_weight_above": "piece weight above {mb} MB",
        "recode.pieces_to_recode": (
            "pieces to recode {count} of {total} ({share}% of the film, {marks}) - "
            "recoding no higher than {ceiling} Mbit/s ahead of time"
        ),
        "recode.report": (
            "recoded {made} pieces ({seconds} s of film), {late} heavy ones went as-is"
        ),
        "recode.rewind": "rewind",
        "recode.head_matters_more": "the head of the run matters more",
        "recode.packing_stuck": "packing got stuck on v{slot}",
        "recode.show_over": "show is over",
        "recode.run_over": "run is over",
        "recode.recoded_pieces": (
            "recoded v{first}...v{last} ({seconds} s of film in {spent} s, {preset}, "
            "{rate}x - plan {plan} from the table)"
        ),
        "recode.yielded_nothing": (
            "recoding v{first}...v{last} did not yield a single piece in {spent} s"
        ),
    }
