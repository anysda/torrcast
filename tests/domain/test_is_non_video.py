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


def test_a_soundtrack_named_by_its_own_word_is_not_a_picture() -> None:
    """🔴 «OST» - слово, которым выдача зовёт саундтрек, и раздача под ним не кино:
    «OST - Настоящий детектив / True Detective [Music From the HBO Series] (2015) AAC».
    Без этого слова разбор звал её фильмом того же года, и склейка тащила её в пул."""
    assert _is_non_video("OST - Настоящий детектив / True Detective (2015) AAC")


def test_a_picture_with_a_soundtrack_attached_is_still_a_picture() -> None:
    """Встречный сторож: «+ OST» рядом с приметой видео - это кино с приложением."""
    assert not _is_non_video("Настоящий детектив (2015) BDRip 1080p + OST")
