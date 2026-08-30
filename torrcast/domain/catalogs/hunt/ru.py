"""Русские надписи кластера пустого поиска."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера пустого поиска.

    Ключа, которого тут нет, продукт скажет по-английски
    (:func:`torrcast.domain.catalogs.phrase.phrase`): русский каталог - надстройка над
    английским, а не второй полный словарь, который обязан поспевать за первым.
    """
    return {
        "hunt.nothing": "по запросу «{query}» ничего не нашлось",
        "hunt.nothing_cut": (
            "по запросу «{query}» ничего не нашлось; каталог сейчас урезан - {gone}"
        ),
        "hunt.banned": "Prowlarr увёл в недоступные {names}",
        "hunt.refused": "отказ у {names}",
        "hunt.silent": "молчит {names}",
    }
