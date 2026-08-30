"""Английские надписи кластера промежутков времени."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера промежутков времени.

    Английский - и умолчание продукта, и запасной каталог: ключа, которого тут нет,
    не существует вовсе, и :func:`torrcast.domain.catalogs.phrase.phrase` на нём падает
    громко, а не отвечает пустотой.
    """
    return {
        "spans.days_hours": "{days} d {hours} h",
        "spans.hours_minutes": "{hours} h {minutes} min",
        "spans.hours": "{hours} h",
        "spans.minutes": "{minutes} min",
    }
