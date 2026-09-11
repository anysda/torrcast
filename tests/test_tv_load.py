"""Проверяет первый LOAD каста «На ТВ» (:mod:`web.tv_load`)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from tests.fakes.receiver import FakeReceiver
from torrcast.domain.position import Position
from torrcast.domain.segment_container import FMP4, MPEGTS
from web.tv_load import tv_load


@dataclass
class _Packed(FakeReceiver):
    """Приёмник с контейнером кусков, как у живого Chromecast; помнит контейнер каждого LOAD."""

    segment_container: str = MPEGTS
    loaded_as: list[str] = field(default_factory=list)
    refuse: bool = False

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        self.loaded_as.append(self.segment_container)
        super().play(url, title, at)
        if self.refuse:
            raise RuntimeError("TV did not start the show: IDLE/ERROR")


def test_the_container_of_the_show_is_set_before_the_load() -> None:
    receiver = _Packed(Position(0.0, 0.0))

    tv_load(receiver, "http://x/index.m3u8", "Breaking Bad", 12.0, FMP4)

    assert receiver.loaded_as == [FMP4]
    assert receiver.plays == [("http://x/index.m3u8", "Breaking Bad", 12.0)]


def test_an_unknown_container_leaves_the_receiver_default() -> None:
    receiver = _Packed(Position(0.0, 0.0))

    tv_load(receiver, "u", "t", 0.0, None)

    assert receiver.loaded_as == [MPEGTS]


def test_a_refused_load_closes_the_link_and_is_raised() -> None:
    receiver = _Packed(Position(0.0, 0.0), refuse=True)

    with pytest.raises(RuntimeError, match="IDLE/ERROR"):
        tv_load(receiver, "u", "t", 0.0, FMP4)

    assert receiver.stops == [True], "отказавший приёмник оставлен с открытым каналом"
