"""Английские надписи кластера юнита показа."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера юнита показа."""
    return {
        "worker.receiver_profile": "receiver profile: {title} - {how}",
        "worker.missing_state_entry": "no state record for {entry_key}",
        "worker.now_playing": "{tag} playing “{title}” from {pos}",
        "worker.next_episode": "next episode: {label}",
    }
