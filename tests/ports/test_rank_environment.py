"""Проверяет форму порта ранжирования."""

from torrcast.ports.rank_environment import RankEnvironment


def test_rank_environment_is_protocol() -> None:
    assert RankEnvironment.__name__ == "RankEnvironment"
