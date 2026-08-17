"""Зеркало :mod:`torrcast.adapters.chromecast.mock.hls_fetch`."""

from __future__ import annotations

from typing import Any

import pytest
import requests

from tests.fakes.clock import FakeClock
from torrcast.adapters.chromecast.mock.hls_fetch import CORS_HEADER, HlsFetch
from torrcast.domain.infra_error import InfraError

URL = "http://127.0.0.1:9/hls/index.m3u8"
BODY = "#EXTM3U\n#EXT-X-ENDLIST\n"


class _Reply:
    """Ответ раздачи на бумаге: столько, сколько от него нужно приёмнику."""

    def __init__(self, text: str = BODY, status_code: int = 200, cors: bool = True) -> None:
        self.text, self.status_code = text, status_code
        self.headers = {CORS_HEADER: "*"} if cors else {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class _Paper:
    """Раздача на бумаге: отвечает заготовкой и помнит, о чём её спросили."""

    def __init__(self, reply: _Reply | None = None, boom: Exception | None = None) -> None:
        self.reply, self.boom = reply or _Reply(), boom
        self.asked: list[str] = []

    def get(self, url: str, timeout: float = 0.0) -> _Reply:
        self.asked.append(url)
        if self.boom is not None:
            raise self.boom
        return self.reply


def _fetch(paper: _Paper, clock: FakeClock, sulk: float = 0.0) -> HlsFetch:
    fetch = HlsFetch("", clock, sulk)
    fetch.session = lambda ca: paper
    return fetch


def test_the_manifest_comes_back_to_the_caller() -> None:
    """Тело манифеста отдаётся зовущему: по нему декодер и считает, с какого куска начать."""
    paper = _Paper()

    assert _fetch(paper, FakeClock()).manifest(URL) == BODY
    assert paper.asked == [URL]


def test_a_reply_without_cors_is_refused_outright() -> None:
    """Ответ без CORS Chromecast молча не играет, поэтому показа на нём нет вовсе."""
    fetch = _fetch(_Paper(_Reply(cors=False)), FakeClock())

    with pytest.raises(InfraError, match=CORS_HEADER):
        fetch.manifest(URL)


def test_a_dead_source_is_named_infrastructure_and_not_a_crash() -> None:
    """Раздача не ответила - это инфраструктурная авария с человеческой причиной."""
    fetch = _fetch(_Paper(boom=requests.ConnectionError()), FakeClock())

    with pytest.raises(InfraError, match="приёмник не забрал манифест"):
        fetch.manifest(URL)


def test_a_404_is_remembered_for_as_long_as_the_profile_says() -> None:
    """Наказание за 404 ставится числом профиля - и снимается им же."""
    clock = FakeClock(1000.0)
    offended = _fetch(_Paper(), clock, sulk=150.0)
    calm = _fetch(_Paper(), clock, sulk=0.0)
    reply: Any = _Reply(status_code=404)

    offended.caught(reply)
    calm.caught(reply)

    assert offended.sulk_until - clock.monotonic() == 150.0, "механизм жив: наказание ставится"
    assert calm.sulk_until <= clock.monotonic(), "нулевое наказание LOAD не задерживает"


def test_an_ordinary_reply_leaves_no_punishment_behind() -> None:
    """Здоровый ответ приёмник не помнит: наказывать не за что."""
    clock = FakeClock(1000.0)
    fetch = _fetch(_Paper(), clock, sulk=150.0)

    fetch.manifest(URL)

    assert fetch.sulk_until == 0.0


def test_a_404_on_the_manifest_both_punishes_and_fails() -> None:
    """404 на манифесте - и наказание приёмнику, и отказ показу: одно другого не отменяет."""
    clock = FakeClock(1000.0)
    fetch = _fetch(_Paper(_Reply(status_code=404)), clock, sulk=150.0)

    with pytest.raises(InfraError):
        fetch.manifest(URL)

    assert fetch.sulk_until - clock.monotonic() == 150.0
