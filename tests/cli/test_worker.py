"""Внутренняя команда ``cast --play-key``: юниту уходит ключ показа и ``--here``."""

from __future__ import annotations

from torrcast.cli.worker import worker
from torrcast.domain.args import Args


class _FakeShow:
    """Запоминает пару довод-за-доводом: ключ показа и решение «играй у меня»."""

    def __init__(self, result: int) -> None:
        self.result = result
        self.requests: list[tuple[str, bool]] = []

    def __call__(self, key: str, here: bool) -> int:
        self.requests.append((key, here))
        return self.result


def test_the_unit_key_is_handed_over_as_a_string() -> None:
    show = _FakeShow(result=0)

    assert worker(Args(query=[], play_key="movie:кино:1999"), show) == 0
    assert show.requests == [("movie:кино:1999", False)]


def test_the_here_flag_is_handed_over_alongside_the_key() -> None:
    show = _FakeShow(result=0)

    assert worker(Args(query=[], play_key="movie:кино:1999", here=True), show) == 0
    assert show.requests == [("movie:кино:1999", True)]


def test_the_code_of_the_show_is_the_code_of_the_command() -> None:
    show = _FakeShow(result=2)

    assert worker(Args(query=[], play_key="movie:кино:1999"), show) == 2
