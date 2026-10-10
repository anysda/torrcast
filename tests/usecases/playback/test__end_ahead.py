"""Зеркало паспорта наперёд: читается в фоне, только по ``go`` и только один раз."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import Media
from torrcast.usecases.playback._end_ahead import END_HEAD, _end_ahead

MEDIA = Media(295.0, (AudioTrack(index=0, language="rus"),), "h264", 1080, 1920)


@pytest.fixture(autouse=True)
def _joined() -> Iterator[None]:
    yield
    for thread in threading.enumerate():
        if thread.name == "end-ahead":
            thread.join(5.0)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, float]]:
    seen: list[tuple[str, float]] = []

    def probe(source: str, timeout: float) -> Media:
        seen.append((source, timeout))
        return MEDIA

    monkeypatch.setattr(_state, "probe", probe, raising=False)
    return seen


def test_nothing_is_read_before_go(calls: list[tuple[str, float]]) -> None:
    """Заведённый паспорт молчит: ни потока, ни чтения, пока показ не скажет ``go``."""
    ahead = _end_ahead("http://ts/stream")

    assert not ahead.done() and calls == []
    assert not [t for t in threading.enumerate() if t.name == "end-ahead"]


def test_go_reads_the_passport_once(calls: list[tuple[str, float]]) -> None:
    """Отрицательная проба: ``go`` без защёлки - щуп зовётся на каждый круг показа."""
    ahead = _end_ahead("http://ts/stream")

    ahead.go()
    ahead.go()

    assert ahead.result(5.0) is MEDIA
    ahead.go()
    assert calls == [("http://ts/stream", END_HEAD)]


def test_an_unread_passport_reaches_the_future(monkeypatch: pytest.MonkeyPatch) -> None:
    def probe(source: str, timeout: float) -> Media:
        raise InfraError("хвост не прочитан")

    monkeypatch.setattr(_state, "probe", probe, raising=False)
    ahead = _end_ahead("http://ts/stream")

    ahead.go()

    with pytest.raises(InfraError):
        ahead.result(5.0)
