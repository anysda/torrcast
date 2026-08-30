"""Русские надписи кластера таблицы релизов."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера таблицы релизов."""
    return {
        "releases.no_query": "что искать? cast releases <запрос>",
        "releases.head": "{title} - раздач {count}",
        "releases.play_specific_many": (
            "играть конкретный: cast <запрос> --pick M --release N [--file N] - "
            "M это номер картины выше, N номер релиза в её таблице"
        ),
        "releases.play_specific_one": "играть конкретный: cast <запрос> --release N [--file N]",
    }
