"""Русские надписи кластера счёта серий."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера счёта серий.

    Ключа, которого тут нет, продукт скажет по-английски
    (:func:`torrcast.domain.catalogs.phrase.phrase`): русский каталог - надстройка над
    английским, а не второй полный словарь, который обязан поспевать за первым.
    """
    return {
        "series.numbering_differs": (
            "нумерации разные: {want} - это счёт по сезонам, а раздача считает"
            " серии насквозь через весь сериал ({span}), не называя сезонов"
            " ({summary}) - нужна раздача, подписанная сезоном: cast <запрос> --release N"
        ),
        "series.episode_absent": (
            "серии {want} в этой раздаче нет ({summary})"
            " - возьми другую раздачу: cast <запрос> --release N"
        ),
        "series.none_found": "серий не нашлось",
        "series.seasons_span": "сезоны {first}-{last} · ",
        "series.episode_count": "{span}серий {count}: {first}...{last}",
    }
