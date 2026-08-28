"""Имена событий склейки ужатого места остаются договором ленты."""

from torrcast.domain.shrunk_splice_events import (
    SHRUNK,
    SHRUNK_SPLICE_ASTRAY,
    SHRUNK_SPLICE_ATTEMPT,
    SHRUNK_SPLICE_FAILED,
    SHRUNK_SPLICE_KEYLESS,
    SHRUNK_SPLICE_NOT_ON_TAPE,
    SHRUNK_SPLICE_NOT_TRIED,
    SHRUNK_SPLICE_SHRINK_FAILED,
    SHRUNK_SPLICE_WON,
)


def test_the_shrunk_splice_tape_vocabulary_stays_stable() -> None:
    """Переименование события не должно молча обнулить счётчик старой боевой ленты."""
    assert SHRUNK == "ужатие на месте"
    assert SHRUNK_SPLICE_ATTEMPT == "попытка склейки ужатого"
    assert SHRUNK_SPLICE_WON == "склейка ужатого вышла"
    assert SHRUNK_SPLICE_FAILED == "склейка ужатого не вышла"
    assert SHRUNK_SPLICE_NOT_TRIED == "склейка ужатого не пробовалась:"
    assert SHRUNK_SPLICE_KEYLESS == "склейка ужатого не пробовалась: нет опорного кадра"
    assert SHRUNK_SPLICE_SHRINK_FAILED == "склейка ужатого не пробовалась: ужать не вышло"
    assert SHRUNK_SPLICE_NOT_ON_TAPE == "склейку ужатого не поставить на ленту показа"
    assert SHRUNK_SPLICE_ASTRAY == "склейка ужатого не с этого места:"
