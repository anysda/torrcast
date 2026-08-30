"""Зеркало отмены выбора: она наша ошибка, но не отказ и не «не нашли»."""

from torrcast.domain.cancelled_error import CancelledError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torrcast_error import TorrcastError


def test_cancelling_unwinds_like_our_errors_but_is_not_a_refusal() -> None:
    """Раскрутка та же (``except TorrcastError`` её видит), а род - другой."""
    error = CancelledError("человек передумал")

    assert isinstance(error, TorrcastError)
    assert not isinstance(error, NotFoundError)
    assert str(error) == "человек передумал"
