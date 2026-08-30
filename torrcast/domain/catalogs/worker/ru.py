"""Русские надписи кластера юнита показа."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера юнита показа."""
    return {
        "worker.receiver_profile": "профиль приёмника: {title} - {how}",
        "worker.missing_state_entry": "в состоянии нет записи {entry_key}",
        "worker.now_playing": "{tag} показ «{title}» с {pos}",
        "worker.next_episode": "следующая серия: {label}",
    }
