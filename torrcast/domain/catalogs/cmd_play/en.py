"""Английский каталог кластера счастливого пути показа."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера счастливого пути показа."""
    return {
        "cmd_play.voice_apart": (
            "the Russian dub sits in a separate file «{base}» - taking it"
        ),
        "cmd_play.resumed_from": " · from {pos}",
        "cmd_play.dry_no_cast": "(--dry) {about} · file «{base}» - not casting",
    }
