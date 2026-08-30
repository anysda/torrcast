"""Русские надписи кластера меню озвучек."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера меню озвучек."""
    return {
        "voices_command.no_query": "что искать? cast voices <запрос>",
        "voices_command.head": "{title} - релиз {number}: {cut}",
        "voices_command.play_specific": (
            "играть конкретную: cast <запрос> --voice N|СТУДИЯ   "
            "(выбор запомнится на картину)"
        ),
    }
