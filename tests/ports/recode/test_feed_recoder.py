"""Зеркало договора кодировщика перед лентой: готовый кусок, придержка и ужатие."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tests.usecases.playback.world import film_keys, grid
from torrcast.ports.recode.encoding_rate import EncodingRate
from torrcast.ports.recode.feed_recoder import FeedRecoder
from torrcast.recode import Encode, Recoder, Weights


@dataclass
class _Pace:
    def table(self) -> tuple[tuple[str, float], ...]:
        return (("veryfast", 1.0), ("ultrafast", 2.0))


@dataclass
class _Recoder:
    """Кодировщик в объёме ленты и ни ручкой шире."""

    spare: Path
    over_wait: float = 5.0
    played: float = 0.0
    done: set[int] = field(default_factory=set)
    pace: _Pace = field(default_factory=_Pace)

    def stop(self) -> None: ...
    def opening(self, slot: int) -> None: ...
    def note(self, slot: int, how: str) -> None: ...

    def holding(self, slot: int, size: int = 0) -> bool:
        return False

    def ready(self, slot: int) -> Path | None:
        return None

    def fit(self, span: float, preset: str) -> EncodingRate:
        return Encode(preset=preset, mbit=4.0)


def test_the_real_recoder_answers_the_named_contract(tmp_path: Path) -> None:
    """Лента спрашивает у настоящего кодировщика место перекода, срок и цель ужатия."""
    weights = Weights.of(film_keys(), grid())
    assert weights is not None
    named: FeedRecoder = Recoder(
        source="http://ts/stream",
        audio=0,
        grid=grid(),
        spare=tmp_path / "recode",
        weights=weights,
        threshold=0.0,
        encode=Encode(preset="ultrafast", mbit=9.0),
    )

    assert named.spare == tmp_path / "recode"
    assert named.over_wait > 0
    assert named.ready(0) is None, "перекода ещё нет - ленте отдавать нечего"
    assert named.fit(15.0, named.pace.table()[-1][0]).mbit > 0


def test_the_feed_asks_for_nothing_it_does_not_call(tmp_path: Path) -> None:
    """Мера ширины: очередь, порог тяжести и подъём потока - не дело ленты.

    Заглушка тут ровно та же по объёму, какой лента обходится в своих зеркалах: отрасти
    договор на ручки показа, и лента начала бы требовать от соседа работу, которой не
    заказывала.
    """
    named: FeedRecoder = _Recoder(spare=tmp_path)

    assert named.holding(0) is False
    assert named.fit(15.0, "ultrafast").mbit == 4.0
