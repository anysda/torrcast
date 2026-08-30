"""Английские надписи кластера пустого поиска."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера пустого поиска.

    Английский - и умолчание продукта, и запасной каталог: ключа, которого тут нет,
    не существует вовсе, и :func:`torrcast.domain.catalogs.phrase.phrase` на нём падает
    громко, а не отвечает пустотой.
    """
    return {
        "hunt.nothing": "nothing was found for “{query}”",
        "hunt.nothing_cut": (
            "nothing was found for “{query}”; the catalogue is cut down right now - {gone}"
        ),
        "hunt.banned": "Prowlarr took {names} out of reach",
        "hunt.refused": "a refusal at {names}",
        "hunt.silent": "{names} keeps silent",
    }
