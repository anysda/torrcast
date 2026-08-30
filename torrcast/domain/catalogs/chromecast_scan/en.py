"""English captions of the Chromecast scan cluster."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Return the English catalog of the Chromecast scan cluster."""
    return {
        "chromecast_scan.searching": "looking for receivers on the network",
        "chromecast_scan.unnamed_device": "receiver",
        "chromecast_scan.subnets_skipped": (
            "subnets too large to scan: {names} - if the TV is in one of them, "
            "give its address by hand: cast --tv <ip>"
        ),
    }
