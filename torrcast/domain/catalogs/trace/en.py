"""Английские надписи кластера ленты меток."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера ленты меток.

    Английский - и умолчание продукта, и запасной каталог: ключа, которого тут нет,
    не существует вовсе, и :func:`torrcast.domain.catalogs.phrase.phrase` на нём падает
    громко, а не отвечает пустотой.
    """
    return {
        "trace.no_marks": "no marks",
        "trace.column_phase": "phase",
        "trace.column_from_zero": "from zero",
        "trace.column_cost": "cost",
        "trace.not_a_number": "a number was expected in the JSON, and {kind} is lying there",
    }
