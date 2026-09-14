"""Зеркало :mod:`web.heard`: какую дорожку карточка отмечает умолчанием."""

import pytest

from tests.usecases.rank.releases import media, track
from web.heard import Heard


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Лестница русская: на ней дубляж и собственная дорожка русского фильма расходятся."""


def test_a_native_picture_marks_its_own_track_and_a_foreign_one_the_dub() -> None:
    tracks = (track(0, "rus", "[DUB] AMALGAMA"), track(1, "rus", None), track(2, "eng", None))

    native = Heard(media(tracks=tracks), native=True, studios=())
    foreign = Heard(media(tracks=tracks), native=False, studios=())

    assert (native.default, foreign.default) == (1, 0)
