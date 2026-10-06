"""English captions of the systemd cluster."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Return the English catalog of the systemd cluster."""
    return {
        "systemd.unit_did_not_start": "unit {unit} did not start: {detail}",
        "systemd.reason_unavailable": "reason unavailable: {reason}",
        "systemd.journal_empty": "the journal is empty",
        "systemd.shelf.warmup_ordered": "shelf {shelf}: warmup ordered for {count} tiles",
        "systemd.shelf.published": "shelf {shelf}: published body with {count} tiles",
        "systemd.shelf.unplayable": 'shelf: "{query}" does not play, tile {tile} is dropped',
        "systemd.shelf.held_shrink": "shelf: body kept, {shelf} has {new} of {old} tiles < {floor}",
        "systemd.shelf.held_drops": (
            "shelf: body kept, {dropped} of {judged} dropped > {ceiling}, {unknown} unknown"
        ),
        "systemd.shelf.feed_short": "shelf: the feed missed an indexer, re-asking for {within} s",
        "systemd.shelf.feed_refilled": "shelf: the re-ask brought {count} rows, missed {missed}",
    }
