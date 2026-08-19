"""Проверки поиска студий в тексте."""

from torrcast.domain.studios_in import studios_in


def test_pack_names_studios_in_track_order() -> None:
    found = studios_in("WEB-DL 1080p, Dub (The Kitchen Russia) + MVO (Good People)")
    assert [studio.name for studio in found] == ["The Kitchen Russia", "Good People"]


def test_same_studio_named_twice_counted_once() -> None:
    assert [s.name for s in studios_in("MVO (HDRezka Studio) / HDRezka")] == ["HDRezka Studio"]


def test_word_inside_word_is_not_a_studio() -> None:
    assert studios_in("Ancordion") == ()
