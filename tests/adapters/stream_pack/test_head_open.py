"""Проверяет размер прогреваемой головы: у mkv её мало, у mp4 там ``moov``."""

from torrcast.adapters.stream_pack.head_open import head_open
from torrcast.domain.warm_open import HEAD_OPEN, HEAD_OPEN_DEFAULT


def test_the_head_is_sized_by_the_container() -> None:
    """У mp4 в голове лежит ``moov``, у mkv - только заголовок: греть их поровну расточительно.

    Продолжение с середины платит эту голову перед каждым показом, и лишние мегабайты
    отбирает полосу у того места, откуда пойдёт картинка.
    """
    assert head_open("mkv") == HEAD_OPEN["mkv"]
    assert head_open("mp4") == HEAD_OPEN["mp4"]
    assert head_open("mkv") < head_open("mp4"), "у mkv голова меньше - это и есть правка"


def test_an_unknown_container_gets_the_cautious_default() -> None:
    """Контейнер не назван - берём с запасом: недогретая голова стоит показу старта."""
    assert head_open("") == HEAD_OPEN_DEFAULT
    assert head_open("ts") == HEAD_OPEN_DEFAULT
