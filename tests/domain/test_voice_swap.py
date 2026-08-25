"""Зеркало честной строки про вынужденную подмену озвучки."""

from __future__ import annotations

from torrcast.domain.voice_swap import voice_swap


def test_the_forced_studio_is_named_together_with_the_one_it_replaced() -> None:
    """Зритель слышит другой дубляж, и строка обязана объяснить оба имени сразу."""
    said = voice_swap("The Kitchen Russia", "TVShows")

    assert said == "озвучка TVShows вместо The Kitchen Russia"


def test_the_same_studio_is_no_substitution_whatever_the_case() -> None:
    """Студию называют и дорожка, и имя раздачи - регистр у них разный, студия та же."""
    assert voice_swap("TVShows", "tvshows") == ""


def test_nothing_is_said_when_there_is_nothing_to_compare() -> None:
    """Ни памяти, ни подмены - и приписывать показу нечего."""
    assert voice_swap("", "TVShows") == ""
    assert voice_swap("The Kitchen Russia", "") == ""
