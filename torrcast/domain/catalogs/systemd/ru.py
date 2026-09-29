"""Русские надписи кластера запуска показа в systemd."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера ``systemd``."""
    return {
        "systemd.unit_did_not_start": "не запустился юнит {unit}: {detail}",
        "systemd.reason_unavailable": "причина недоступна: {reason}",
        "systemd.journal_empty": "в журнале пусто",
        "systemd.shelf.warmup_ordered": "полка {shelf}: заказан прогрев {count} плиток",
        "systemd.shelf.published": "полка {shelf}: опубликовано тело из {count} плиток",
    }
