"""Жива ли служба раздач: ``/echo`` за короткий срок, любой сетевой отказ - «нет»."""

from __future__ import annotations

import pytest
import requests

from torrcast.adapters.torrserver.echoed import PROBE_TIMEOUT, echoed


class _Session:
    def __init__(self, fail: Exception | None = None) -> None:
        self._fail = fail
        self.asked: list[tuple[str, float]] = []

    def get(self, url: str, timeout: float) -> _Session:
        self.asked.append((url, timeout))
        if self._fail is not None:
            raise self._fail
        return self

    def raise_for_status(self) -> None:
        return None

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_a_service_answering_echo_is_alive() -> None:
    session = _Session()

    assert echoed(session, "http://127.0.0.1:8090")  # type: ignore[arg-type]
    assert session.asked == [("http://127.0.0.1:8090/echo", PROBE_TIMEOUT)]


@pytest.mark.parametrize(
    "fail",
    [requests.ReadTimeout("slow"), requests.ConnectionError("refused"), requests.HTTPError("500")],
    ids=["hung", "refused", "bad"],
)
def test_a_service_failing_echo_is_dead(fail: Exception) -> None:
    assert not echoed(_Session(fail), "http://127.0.0.1:8090")  # type: ignore[arg-type]
