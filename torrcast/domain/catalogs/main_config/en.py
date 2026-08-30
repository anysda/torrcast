"""English captions of the main configuration file cluster."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Return the English catalog of the main configuration file cluster."""
    return {
        "main_config.unreadable": "broken config {path}: {reason}",
        "main_config.not_an_object": "broken config {path}: expected a JSON object",
        "main_config.write_failed": "could not write {path}: {reason}",
    }
