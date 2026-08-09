"""Тест на детерминированность разрешения ничьих (TC-227)."""

from __future__ import annotations

import random
from typing import Any

from torrcast.cli import rank_releases
from torrcast.parse import Release, cluster, menu_order


def test_deterministic_ties() -> None:
    """Один и тот же набор раздач, перетасованный, должен давать один и тот же результат:
    верхний релиз картины, порядок меню франшиз и дефолт.
    """
    releases = []
    # 3 картины (Movie 0, Movie 1, Movie 2) по 5 раздач в каждой.
    # У всех раздач одинаковый размер, сиды, качество, чтобы вызвать ничью во всех сортировках.
    for p in range(3):
        for i in range(5):
            releases.append(
                Release(
                    raw_name=f"Movie {p} 2021 1080p variant {i}",
                    title=f"Movie {p}",
                    year=2021,
                    size=10**9,
                    seeders=100,
                    magnet=f"magnet:?xt=urn:btih:{p}{i:039x}",
                    kind="movie",
                    codec="H.264",
                    quality="1080p",
                )
            )

    def run_flow(rels: list[Release]) -> tuple[Any, ...]:
        pictures = cluster(rels)
        ordered = menu_order(pictures)

        snapshot = []
        for pic in ordered:
            ranked = rank_releases(pic.releases, runtime=7200, warn_mbit=15.0)
            snapshot.append(
                (
                    pic.title,
                    pic.year,
                    pic.best_release.magnet if pic.best_release else None,
                    [r.magnet for r in ranked],
                )
            )
        return tuple(snapshot)

    expected = run_flow(releases)

    reversed_rels = list(reversed(releases))
    assert run_flow(reversed_rels) == expected, "Перевёрнутый порядок сломал ранжир"

    rng = random.Random(42)
    for _ in range(10):
        shuffled = list(releases)
        rng.shuffle(shuffled)
        assert run_flow(shuffled) == expected, "Случайный порядок сломал ранжир"
