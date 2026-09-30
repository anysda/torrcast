"""Внутренняя команда ``cast --play-key``: юниту уходят ключ показа, ``--here`` и ``--tab``."""

from __future__ import annotations

from torrcast.cli.worker import worker
from torrcast.domain.args import Args


class _FakeShow:
    """Запоминает доводы по порядку: ключ показа, «играй у меня» и ключ вкладки."""

    def __init__(self, result: int) -> None:
        self.result = result
        self.requests: list[tuple[str, bool, str]] = []

    def __call__(self, key: str, here: bool, tab: str) -> int:
        self.requests.append((key, here, tab))
        return self.result


def test_the_unit_key_is_handed_over_as_a_string() -> None:
    show = _FakeShow(result=0)

    assert worker(Args(query=[], play_key="movie:кино:1999"), show) == 0
    assert show.requests == [("movie:кино:1999", False, "")]


def test_the_here_flag_is_handed_over_alongside_the_key() -> None:
    show = _FakeShow(result=0)

    assert worker(Args(query=[], play_key="movie:кино:1999", here=True), show) == 0
    assert show.requests == [("movie:кино:1999", True, "")]


def test_the_tab_key_is_handed_over_alongside_here() -> None:
    show = _FakeShow(result=0)
    args = Args(query=[], play_key="movie:кино:1999", here=True, tab="gecko-linux")

    assert worker(args, show) == 0
    assert show.requests == [("movie:кино:1999", True, "gecko-linux")]


def test_the_code_of_the_show_is_the_code_of_the_command() -> None:
    show = _FakeShow(result=2)

    assert worker(Args(query=[], play_key="movie:кино:1999"), show) == 2
