"""Зеркало догадки справки: чем доказывается имя добора и когда за ним не идут вовсе."""

from __future__ import annotations

from torrcast.domain.facts.origin import Origin
from torrcast.usecases.discover._second_hearsay import _second_hearsay


def test_a_name_named_outright_is_no_hearsay() -> None:
    """Справка назвала статью по имени - доказывать нечего, идём как шли."""
    assert _second_hearsay("солтберн", "Saltburn", Origin(title="Saltburn")) is False


def test_the_same_picture_under_another_transcription_confirms_itself() -> None:
    """«Сальтберн» и «Солтберн» - одно имя разной транскрипцией: признак есть."""
    about = Origin(title="Saltburn", name="Солтберн", guessed=True)

    assert _second_hearsay("сальтберн", "Saltburn", about) is False


def test_another_word_in_the_name_is_another_picture() -> None:
    """🔴 TC-253. «Все мы незнакомцы» против «Все мы убийцы» - за ней не идут вовсе."""
    about = Origin(title="Nous sommes tous des assassins", name="Все мы убийцы", guessed=True)

    assert _second_hearsay("все мы незнакомцы", about.title, about) is None


def test_a_guess_with_no_russian_name_to_check_against_is_taken_with_a_line() -> None:
    """Своего русского имени у статьи нет - сверить было не с чем, и это говорят вслух."""
    about = Origin(title="Blue Exorcist", guessed=True)

    assert _second_hearsay("синий экзорцист", "Blue Exorcist", about) is True
