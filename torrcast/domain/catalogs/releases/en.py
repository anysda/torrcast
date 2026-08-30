"""Английские надписи кластера таблицы релизов."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера таблицы релизов."""
    return {
        "releases.no_query": "what to search for? cast releases <query>",
        "releases.head": "{title} - releases {count}",
        "releases.play_specific_many": (
            "play a specific one: cast <query> --pick M --release N [--file N] - "
            "M is the picture number above, N is the release number in its table"
        ),
        "releases.play_specific_one": "play a specific one: cast <query> --release N [--file N]",
    }
