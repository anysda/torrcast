"""Зеркало :mod:`torrcast.domain.normalize`: имя раздачи, приведённое к одному виду."""

from torrcast.domain.normalize import _normalize


def test_the_many_kinds_of_dash_become_one() -> None:
    """Трекеры пишут тире четырьмя знаками, а разбор имени умеет читать один."""
    assert _normalize("Брат — Brother – 1997") == "Брат - Brother - 1997"


def test_the_russian_letter_of_the_resolution_becomes_the_latin_one() -> None:
    """«1080 р» и «1080p» - одно и то же качество, и различать их незачем."""
    assert _normalize("Брат 1080 р") == "Брат 1080p"


def test_the_spaces_of_every_kind_collapse_into_one() -> None:
    assert _normalize("  Брат\xa0\xa0 1997  ") == "Брат 1997"
