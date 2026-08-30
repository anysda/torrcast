"""Английские надписи кластера меню озвучек."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера меню озвучек."""
    return {
        "voices_command.no_query": "what to search for? cast voices <query>",
        "voices_command.head": "{title} - release {number}: {cut}",
        "voices_command.play_specific": (
            "play a specific one: cast <query> --voice N|STUDIO   "
            "(the choice will be remembered for the picture)"
        ),
    }
