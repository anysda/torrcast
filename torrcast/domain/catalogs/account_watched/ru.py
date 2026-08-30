"""Русские надписи кластера бухгалтерии досмотра."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера бухгалтерии досмотра."""
    return {
        "account_watched.next_label": "играю {label}",
        "account_watched.from_start": "играю с начала",
        "account_watched.done": "«{title}»{what} досмотрено на {stopped} из {dur} - {decision}",
    }
