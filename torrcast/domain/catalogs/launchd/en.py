"""English captions of the launchd cluster."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Return the English catalog of the launchd cluster."""
    return {
        "launchd.job_did_not_start": "job {job} did not start: {detail}",
        "launchd.reason_unavailable": "reason unavailable: {reason}",
        "launchd.log_empty": "the log is empty",
    }
