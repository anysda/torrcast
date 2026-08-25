"""Зеркало :mod:`torrcast.domain.cluster`: сырая выдача трекеров, собранная в картины."""

from torrcast.domain.cluster import cluster
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _found(title: str, original: str | None, year: int, magnet: str) -> Release:
    return Release(
        raw_name=f"{title} {year}", title=title, original=original, year=year, magnet=magnet
    )


def test_the_two_names_of_one_picture_end_up_in_one_bucket() -> None:
    """Трекеры зовут картину по-русски и латиницей; зрителю нужен один пункт, а не два."""
    found = cluster(
        [
            _found("Брат", "Brother", 1997, "m1"),
            _found("Brother", None, 1997, "m2"),
        ]
    )

    assert [(p.title, len(p.releases)) for p in found] == [("Брат", 2)]


def test_different_pictures_stay_different() -> None:
    found = cluster([_found("Брат", None, 1997, "m1"), _found("Сестра", None, 2019, "m2")])

    assert [p.title for p in found] == ["Брат", "Сестра"]


def test_one_name_in_two_years_is_two_pictures() -> None:
    """Тёзка другого года - другая картина: год тут разводит, а не собирает."""
    found = cluster([_found("Брат", None, 1997, "m1"), _found("Брат", None, 2019, "m2")])

    assert [(p.title, p.year) for p in found] == [("Брат", 1997), ("Брат", 2019)]


def test_the_glue_rule_has_the_last_word_over_the_buckets() -> None:
    """Склейка франшиз приходит доводом: сборка её решение не переигрывает."""
    seen: list[int] = []

    def keep_the_first(pictures: list[Picture]) -> list[Picture]:
        seen.append(len(pictures))
        return pictures[:1]

    found = cluster(
        [_found("Брат", None, 1997, "m1"), _found("Сестра", None, 2019, "m2")],
        glue_rule=keep_the_first,
    )

    assert seen == [2]
    assert len(found) == 1
