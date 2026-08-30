"""English captions of the console cluster."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Return the English catalog of the console cluster."""
    return {
        "console.need_number": "need a number from 1 to {count}",
        "console.need_number_no_terminal": (
            "need a number from 1 to {count}, and there is no terminal"
        ),
        "console.no_terminal_default": "(no terminal - taking the default)",
        "console.seconds": "s",
    }
