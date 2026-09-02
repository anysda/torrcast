"""Зеркало строки взятия сериала: названы обе стороны смены картины."""

from tests.usecases.choice.world import plan
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice.series_taken_line import series_taken_line


def test_the_taken_series_the_left_film_and_the_menu_door_are_named() -> None:
    """🔴 Молчаливая замена картины - худший вид брака: фильм назван вслух вместе с дверью."""
    master = [
        plan("Мастер и Маргарита", 2024, seeders=300),
        plan("Мастер и Маргарита", 2005, kind="tv", seeders=40),
    ]

    assert series_taken_line(master, 2, "мастер и маргарита") == phrase(
        "choice.series_taken",
        picture=f"Мастер и Маргарита (2005{phrase('choice.series_mark')})",
        other="Мастер и Маргарита (2024)",
        asked="мастер и маргарита",
    )
