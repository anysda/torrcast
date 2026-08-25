"""Зеркало :mod:`torrcast.domain.looks_anime`: аниме, узнанное по самому имени раздачи."""

from torrcast.domain.looks_anime import looks_anime


def test_the_word_of_the_genre_names_the_anime() -> None:
    """Источник аниме бывает обычным трекером - тогда об этом говорит только имя."""
    assert looks_anime("Наруто аниме 1080p")
    assert looks_anime("Naruto OVA")


def test_an_ordinary_film_does_not_look_like_anime() -> None:
    assert not looks_anime("Брат 1997 BDRip")
