"""Тест на детерминированность разрешения ничьих (TC-227)."""

from __future__ import annotations

import random
from typing import Any

from torrcast.cli import rank_releases
from torrcast.domain.cluster import cluster
from torrcast.domain.menu_order import menu_order
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.release import Release


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


def test_short_query_tie_uses_release_count_then_key() -> None:
    """Равные по длине имена выбираются по числу раздач и алфавиту, не по входу."""
    releases = [
        Release(raw_name="Девять песен", title="Девять песен", year=2004, kind="movie"),
        Release(raw_name="Девять миров", title="Девять миров", year=2009, kind="movie"),
        Release(raw_name="Девять ярдов", title="Девять ярдов", year=2000, kind="movie"),
        Release(raw_name="Девять ярдов 1080p", title="Девять ярдов", year=2000, kind="movie"),
    ]

    def picked(pool: list[Release]) -> tuple[str, ...]:
        return tuple(p.title for p in pick_franchise("девять", cluster(pool)))

    assert picked(releases) == ("Девять ярдов",)
    assert picked(list(reversed(releases))) == ("Девять ярдов",)

    tied = releases[:-1]
    assert picked(tied) == ("Девять миров",)
    assert picked(list(reversed(tied))) == ("Девять миров",)


def test_word_match_tie_uses_release_count_then_key() -> None:
    """Словесная ступень разрешает такую же ничью тем же устойчивым правилом."""
    releases = [
        Release(raw_name="Алый тихий берег", title="Алый тихий берег", kind="movie"),
        Release(raw_name="Алый новый берег", title="Алый новый берег", kind="movie"),
        Release(raw_name="Алый новый берег 1080p", title="Алый новый берег", kind="movie"),
    ]

    found = pick_franchise("алый берег", cluster(releases))
    assert [p.title for p in found] == ["Алый новый берег"]
