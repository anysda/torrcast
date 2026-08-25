"""Зеркало :mod:`torrcast.domain.parse_voices`: какие озвучки обещает имя раздачи."""

from torrcast.domain.parse_voices import _parse_voices


def test_a_voice_named_by_a_word_is_found() -> None:
    """Без русской дорожки релиз негоден, и первым о ней говорит имя раздачи."""
    assert _parse_voices("Брат 1997 [Дубляж]") == ("Дубляж",)


def test_the_letter_tags_after_the_slash_are_voices_too() -> None:
    """Трекеры пишут озвучки одной буквой в хвосте: это тот же список, только короче."""
    assert _parse_voices("Кино 1080p | D, A") == ("Дубляж", "Авторский")


def test_the_same_voice_named_twice_is_named_once() -> None:
    assert _parse_voices("Кино Дубляж Dub") == ("Дубляж",)


def test_a_name_that_promises_no_voice_promises_nothing() -> None:
    assert _parse_voices("Кино 1997 BDRip") == ()
