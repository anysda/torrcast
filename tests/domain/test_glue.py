"""Зеркало :mod:`torrcast.domain.glue`: тёзки, сведённые в одну картину."""

from torrcast.domain.glue import glue
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(title: str, year: int | None, original: str | None = None) -> Picture:
    return Picture(
        title=title,
        year=year,
        original=original,
        releases=[Release(raw_name=f"{title} {year}", title=title, original=original)],
    )


def test_namesakes_of_neighbouring_years_become_one_picture() -> None:
    """Год у раздач одной картины расходится на единицу: это она же, а не вторая."""
    found = glue([_picture("Брат", 1997), _picture("Брат", 1998)])

    assert len(found) == 1
    assert len(found[0].releases) == 2


def test_namesakes_of_distant_years_stay_two_pictures() -> None:
    """Между 1997 и 2019 - другое кино с тем же именем, и склейка была бы подменой."""
    found = glue([_picture("Брат", 1997), _picture("Брат", 2019)])

    assert len(found) == 2


def test_different_names_are_never_glued() -> None:
    found = glue([_picture("Брат", 1997), _picture("Сестра", 1998)])

    assert sorted(p.title for p in found) == ["Брат", "Сестра"]


def test_the_three_d_copy_is_the_same_picture() -> None:
    """«Аватар» и «Аватар 3D» - одна картина, показанная по-разному."""
    found = glue([_picture("Аватар", 2009), _picture("Аватар 3D", 2009)])

    assert len(found) == 1
