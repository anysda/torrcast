"""Английские надписи кластера бухгалтерии досмотра."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера бухгалтерии досмотра."""
    return {
        "account_watched.next_label": "playing {label}",
        "account_watched.from_start": "playing from the start",
        "account_watched.done": "“{title}”{what} watched to {stopped} of {dur} - {decision}",
    }
