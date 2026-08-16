"""Зеркально проверяет штатный конец показа по SIGTERM."""

import pytest

from torrcast.usecases.stopped import _on_term, _Stopped


def test_sigterm_is_a_successful_end_not_a_failure() -> None:
    assert issubclass(_Stopped, KeyboardInterrupt)
    with pytest.raises(_Stopped):
        _on_term(15, None)
