"""Контракт команды ключа JacRed: значение передаётся, но не печатается."""

from torrcast.cli.jacred_key import jacred_key
from torrcast.domain.args import Args


def test_the_key_reaches_its_saver() -> None:
    saved: list[str] = []

    def remember(key: str) -> int:
        saved.append(key)
        return 0

    assert jacred_key(Args(query=[], jacred_key="test-key"), remember) == 0
    assert saved == ["test-key"]
