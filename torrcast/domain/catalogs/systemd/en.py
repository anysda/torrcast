"""English captions of the systemd cluster."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Return the English catalog of the systemd cluster."""
    return {
        "systemd.unit_did_not_start": "unit {unit} did not start: {detail}",
        "systemd.reason_unavailable": "reason unavailable: {reason}",
        "systemd.journal_empty": "the journal is empty",
    }
