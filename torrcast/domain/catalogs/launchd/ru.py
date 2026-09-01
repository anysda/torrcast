"""Русские надписи кластера запуска показа в launchd."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера ``launchd``."""
    return {
        "launchd.job_did_not_start": "не запустилось задание {job}: {detail}",
        "launchd.reason_unavailable": "причина недоступна: {reason}",
        "launchd.log_empty": "в журнале пусто",
    }
