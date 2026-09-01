"""Русские надписи кластера обновления."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера обновления."""
    return {
        "upgrade.needs_root": "нужен root: запусти cast --upgrade от root",
        "upgrade.elevating": "не root - перезапуск через sudo",
        "upgrade.no_loader": (
            "эта копия поставлена раньше, чем появился cast --upgrade; обнови её один раз"
            " командой curl -fsSL https://torrcast.anysda.space | sh"
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
