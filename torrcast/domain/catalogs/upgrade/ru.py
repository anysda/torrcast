"""Русские надписи кластера обновления."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера обновления."""
    return {
        "upgrade.needs_root": "нужен root: sudo cast --upgrade",
        "upgrade.no_loader": (
            "эта копия поставлена раньше, чем появился cast --upgrade; обнови её один раз"
            ' командой sudo sh -c "curl -fsSL https://torrcast.anysda.space | sh"'
        ),
        "upgrade.show_is_on": (
            "сейчас играет «{what}», а обновление перезапускает юниты, которыми показ"
            " держится - сними каст: cast stop"
        ),
        "upgrade.show_is_on_unnamed": (
            "сейчас идёт показ, а обновление перезапускает юниты, которыми он держится"
            " - сними каст: cast stop"
        ),
        "upgrade.failed": "обновление не прошло - установленным остался torrcast {version}",
    }
