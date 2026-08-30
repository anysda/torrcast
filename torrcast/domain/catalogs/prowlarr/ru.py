"""Русские надписи кластера отказов Prowlarr."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера ``prowlarr``."""
    return {
        "prowlarr.unexpected_answer": "Prowlarr вернул неожиданный ответ",
        "prowlarr.all_indexers_unavailable": (
            "Prowlarr увёл в недоступные все индексеры ({names}) - каталога сейчас нет"
        ),
        "prowlarr.selected_indexers_unresponsive": "Prowlarr: выбранные индексеры не отвечают",
        "prowlarr.unresponsive": "Prowlarr не отвечает ({base_url}): {reason}",
        "prowlarr.not_json": "Prowlarr вернул не JSON",
    }
