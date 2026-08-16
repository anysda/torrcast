"""Проверки протокола приёмника."""

from torrcast.domain.receiver import Receiver


def test_protocol_is_runtime_checkable() -> None:
    assert isinstance(object(), Receiver) is False
