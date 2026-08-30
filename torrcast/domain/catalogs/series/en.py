"""Английские надписи кластера счёта серий."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера счёта серий.

    Английский - и умолчание продукта, и запасной каталог: ключа, которого тут нет,
    не существует вовсе, и :func:`torrcast.domain.catalogs.phrase.phrase` на нём падает
    громко, а не отвечает пустотой.
    """
    return {
        "series.numbering_differs": (
            "the numbering differs: {want} counts by seasons, while the swarm counts episodes"
            " straight through the whole show ({span}), never naming a season ({summary})"
            " - you need a swarm signed with a season: cast <query> --release N"
        ),
        "series.episode_absent": (
            "episode {want} is not in this swarm ({summary})"
            " - take another swarm: cast <query> --release N"
        ),
        "series.none_found": "no episodes found",
        "series.seasons_span": "seasons {first}-{last} · ",
        "series.episode_count": "{span}episodes {count}: {first}...{last}",
    }
