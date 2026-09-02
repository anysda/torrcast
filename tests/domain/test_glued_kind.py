"""Зеркало :mod:`torrcast.domain.glued_kind`: вид склеенной картины."""

from torrcast.domain.glued_kind import _glued_kind
from torrcast.domain.picture import Picture


def test_a_series_in_the_glue_outweighs_a_film() -> None:
    """🔴 Серийная метка - улика, а её отсутствие уликой не бывает: сериал перевешивает."""
    merged = [
        Picture(title="Тачки Мультачки: Байки Мэтра", year=2006),
        Picture(title="Байки Мэтра", year=2008, kind="tv"),
    ]

    assert _glued_kind(merged) == "tv"


def test_the_number_of_releases_does_not_decide_the_kind() -> None:
    """Кучка фильма шла первой и была больше - вид решался ею, а число раздач о виде молчит."""
    merged = [
        Picture(title="Байки Мэтра", year=2008, kind="tv"),
        Picture(title="Байки Мэтра", year=2006),
    ]

    assert _glued_kind(merged) == "tv"


def test_a_glue_without_a_series_keeps_the_kind_it_had() -> None:
    twice = [Picture(title="Брат", year=1997), Picture(title="Брат", year=1997)]

    assert _glued_kind(twice) == "movie"


def test_a_glue_of_one_picture_answers_by_that_picture() -> None:
    assert _glued_kind([Picture(title="Обложка", year=None, kind="other")]) == "other"
