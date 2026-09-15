"""Зеркало :func:`torrcast.domain.foreign_work.foreign_work`."""

from __future__ import annotations

import pytest

from torrcast.domain.foreign_work import foreign_work
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _release(original: str | None) -> Release:
    return Release(raw_name="x", title="x", original=original)


@pytest.mark.parametrize(
    ("picture", "release", "foreign"),
    [
        ("Naruto", "Naruto: Shippuuden", True),
        ("Rick and Morty", "Rick and Morty: The Anime", True),
        ("Shingeki no Kyojin", "Shingeki no Kyojin OAD", True),
        ("Naruto", "Naruto", False),
        ("Re:Zero kara Hajimeru Isekai", "Re:Zero kara Hajimeru Isekai 2nd", False),
        ("Shingeki no Kyojin", "Shingeki no Kyojin: The Final Season", False),
        ("Shingeki no Kyojin", "Attack on Titan", False),
        ("Naruto", None, False),
        (None, "Naruto: Shippuuden", False),
    ],
)
def test_another_work_is_told_by_the_words_that_continue_the_original(
    picture: str | None, release: str | None, foreign: bool
) -> None:
    """Продолжение оригинала словами работы - чужое, словами сезона - своё."""
    card = Picture(title="x", year=2002, kind="tv", original=picture)

    assert foreign_work(_release(release), card) is foreign
