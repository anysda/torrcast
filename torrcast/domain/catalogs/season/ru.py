"""Русские надписи кластера перехода через границу сезона."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера перехода через границу сезона."""
    return {
        "season.searching_next": "«{title}» - сезон {season} досмотрен, ищу сезон {upcoming}",
        "season.no_next_found": "«{title}» - сезон {season} последний: {err}",
        "season.search_failed": "«{title}» - сезон {upcoming} не найти: {err}",
        "season.no_releases_found": (
            "«{title}» - сезон {season} последний: раздач сезона {upcoming} не нашлось"
        ),
        "season.could_not_start": "«{title}» - сезон {upcoming} не поднялся: {err}",
    }
