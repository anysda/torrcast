"""Проверки распознавания студии."""

from torrcast.domain.studio_of import studio_of


def test_longest_known_name_wins() -> None:
    studio = studio_of("MVO (HDRezka Studio)")
    assert studio is not None
    assert studio.name == "HDRezka Studio"
