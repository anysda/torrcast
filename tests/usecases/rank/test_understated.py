"""Чем подтверждённый кадр хуже обещанного: строка обязана назвать обе цифры."""

from __future__ import annotations

from tests.usecases.rank.releases import media, rel
from torrcast.usecases.rank.understated import understated


def test_a_name_promising_more_names_both_numbers() -> None:
    said = understated(rel(quality="1080p"), media(height=574, width=1150))
    assert said == "назван 1080p, на деле 574p"


def test_an_honest_release_says_nothing() -> None:
    assert understated(rel(quality="1080p"), media()) == ""


def test_a_silent_name_is_judged_by_hd() -> None:
    """Верхний кандидат «Моаны 2»: ни одной цифры в заголовке, а внутри 1150x574."""
    assert understated(rel(quality=None), media(height=574, width=1150)) == "на деле 574p"
    assert understated(rel(quality=None), media()) == ""


def test_a_silent_passport_is_not_a_verdict() -> None:
    assert understated(rel(quality="1080p"), media(height=0, width=0)) == ""


def test_a_progressive_promise_over_an_interlaced_stream_is_a_substitution() -> None:
    """Разрешение тут не врёт, поэтому высотой подмену не поймать - только буквой."""
    said = understated(rel(quality="1080p"), media(field_order="tt"))
    assert said == "назван 1080p, на деле 1080i"
