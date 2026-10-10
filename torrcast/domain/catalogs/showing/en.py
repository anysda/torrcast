"""Английские надписи кластера занятого телевизора."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера занятого телевизора."""
    return {
        "showing.at": "at {pos}",
        "showing.busy_tv": (
            "the TV is already showing {what}{where}. Pick a picture and this show "
            "will be interrupted; while you pick, it keeps playing as it was."
        ),
        "showing.busy_browser": (
            "the browser is already showing {what}{where}. Pick a picture and this show "
            "will be interrupted; while you pick, it keeps playing as it was."
        ),
    }
