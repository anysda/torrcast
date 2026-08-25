"""Зеркало :mod:`torrcast.domain.catalog_has_name`: есть ли спрошенное имя в каталоге."""

from torrcast.domain.catalog_has_name import catalog_has_name
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def test_the_asked_title_is_found_by_either_of_the_two_names() -> None:
    """Каталог отвечает на оба имени картины: спрашивают её и так, и так."""
    pictures = [Picture(title="Брат", year=1997, original="Brother")]

    assert catalog_has_name("Брат", pictures)
    assert catalog_has_name("brother", pictures)


def test_the_franchise_name_answers_for_its_first_part() -> None:
    """«Матрица» - это про первую часть: продолжение само собой её имя не занимает."""
    first = Picture(title="Матрица: Перезагрузка", year=2003, part=1)
    second = Picture(title="Матрица: Перезагрузка", year=2003, part=2)

    assert catalog_has_name("Матрица", [first])
    assert not catalog_has_name("Матрица", [second])


def test_a_name_two_releases_repeat_counts_as_a_name_of_the_catalogue() -> None:
    """Одна раздача с чужим именем - опечатка, две - имя, которым картину и зовут."""
    lone = Picture(
        title="Брат", year=1997, releases=[Release(raw_name="x", title="Брат", aliases=("Bratan",))]
    )
    twice = Picture(
        title="Брат",
        year=1997,
        releases=[
            Release(raw_name="x", title="Брат", aliases=("Bratan",)),
            Release(raw_name="y", title="Брат", aliases=("Bratan",)),
        ],
    )

    assert not catalog_has_name("Bratan", [lone])
    assert catalog_has_name("Bratan", [twice])


def test_a_number_after_the_franchise_is_not_part_of_the_asked_name() -> None:
    """Номер части - отдельный вопрос, и имя каталога он не удлиняет."""
    assert catalog_has_name("Брат 2", [Picture(title="Брат", year=1997)])


def test_a_name_the_catalogue_never_heard_is_not_found() -> None:
    assert not catalog_has_name("Сестра", [Picture(title="Брат", year=1997)])
    assert not catalog_has_name("  ", [Picture(title="Брат", year=1997)])
