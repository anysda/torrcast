"""Зеркало :mod:`torrcast.domain.is_non_video`: раздача, в которой кино нет вовсе."""

from torrcast.domain.is_non_video import _is_non_video


def test_music_and_books_are_not_pictures() -> None:
    """Выдача трекера полна не-кино, и включать такое нельзя даже по точному имени."""
    assert _is_non_video("Брат саундтрек FLAC")
    assert _is_non_video("Брат аудиокнига")


def test_a_video_mark_beats_the_non_video_one() -> None:
    """Имя говорит и «PC», и «1080p» - это кино с приложенной игрой, а не игра."""
    assert not _is_non_video("Брат PC 1080p BDRip")


def test_an_ordinary_release_is_not_flagged() -> None:
    assert not _is_non_video("Брат 1997 BDRip")
