"""Проверяет подключение порта уточнения."""

from torrcast.usecases import reinforce


def test_reinforce_accepts_environment() -> None:
    assert not reinforce.same_picture(None, None, object(), False)
