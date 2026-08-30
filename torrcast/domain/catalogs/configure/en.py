"""Английские надписи кластера настройки телевизора."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера настройки телевизора."""
    return {
        "configure.headless_note": " (headless receiver, no casting out)",
        "configure.tv_line": "TV: {name}{address}{note}",
        "configure.no_receivers_found": (
            "found no receivers on the network - is the TV on and on the same network? "
            "you can also set the address by hand: cast --tv <ip>"
        ),
        "configure.found_no_terminal": (
            "found {count} receivers, and there is no terminal - not choosing blindly; "
            "name the address yourself: cast --tv <ip>"
        ),
        "configure.which_tv": "Which TV?",
    }
