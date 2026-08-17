"""Проверяет паспорт картины и сверку двух паспортов на одну ли они картину."""

from torrcast.domain.facts.origin import Origin, _same_picture_origin


def test_the_passport_is_empty_until_a_name_or_a_year_is_known() -> None:
    """Q-идентификатор и отметка источника в паспорт не входят: на показ они не влияют."""
    assert not Origin()
    assert not Origin(entity="Q1", source="wiki")
    assert Origin(title="Cars")
    assert Origin(year=2006)
    assert Origin(name="Тачки")


def test_two_passports_are_one_picture_when_the_original_or_the_year_agree() -> None:
    """Русское имя у обоих одно - различают картины оригинал и год."""
    movie = Origin(title="Deadwood: The Movie", year=2006, name="Дедвуд")
    show = Origin(title="Deadwood", year=2004, name="Дедвуд")
    assert not _same_picture_origin(movie, show), "ни оригинал, ни год не сошлись"
    assert _same_picture_origin(movie, Origin(title="deadwood the movie", name="Дедвуд"))
    assert _same_picture_origin(show, Origin(year=2004, name="Дедвуд"))


def test_an_empty_original_never_counts_as_an_agreement() -> None:
    """У отечественной картины оригинала нет вовсе - пустое с пустым не сходится."""
    assert not _same_picture_origin(Origin(name="Брат"), Origin(name="Брат"))
