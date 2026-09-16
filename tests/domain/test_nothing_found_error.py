"""Проверки отказа, которому нечего объяснить."""

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.nothing_found_error import NothingFoundError


def test_is_a_not_found_error() -> None:
    """Ловившие «ничего не нашлось» одним родом продолжают ловить его и теперь."""
    assert issubclass(NothingFoundError, NotFoundError)
