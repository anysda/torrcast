"""Зеркало :mod:`torrcast.domain.release`."""

from torrcast.domain.release import Release


def test_release_is_exposed() -> None:
    assert Release is not None


def test_studios_come_from_the_marks_not_from_the_title() -> None:
    release = Release(
        raw_name="Гоблин / Goblin (2020) BDRip 1080p, Dub (The Kitchen Russia)",
        title="Гоблин",
        original="Goblin",
    )
    assert [studio.name for studio in release.studios] == ["The Kitchen Russia"]
