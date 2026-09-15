"""Зеркало :mod:`hass.hit_claims`: один приговор на картину и промах, который не промах."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from hass.hit_claims import _ATTEMPTS, _RETRY
from hass.hit_posters import FIELD, HitPosters
from hass.poster_shelf import PosterShelf
from tests.test_hit_posters import FakeSource, _row
from torrcast.domain.facts.ask import Ask
from torrcast.domain.json_value import JsonValue

_SETTLE = 5.0


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@dataclass
class _Storm:
    """Погода источника: 429 идут, пока ``troubled``, тишина до ``calm``."""

    troubled: bool = True
    calm: float = 0.0

    def troubled_since(self, moment: float) -> bool:
        return self.troubled

    def calm_at(self) -> float:
        return self.calm


class _GatedSource(FakeSource):
    """Приговор стоит, пока проба не откроет ворота: так двое спрашивают одновременно."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.opened = threading.Event()

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        self.entered.set()
        self.opened.wait(_SETTLE)
        return super().wanted(asks, timeout)


def _posters(tmp_path: Path, source: FakeSource, clock: _Clock, storm: _Storm) -> HitPosters:
    return HitPosters(source, PosterShelf(home=lambda: tmp_path), clock, storm)


@pytest.mark.machine
def test_the_preview_and_the_final_share_one_verdict(tmp_path: Path) -> None:
    """Второй спросивший о той же картине ждёт идущий приговор, а не зовёт свой."""
    source = _GatedSource()
    posters = HitPosters(source, PosterShelf(home=lambda: tmp_path))
    said: list[list[JsonValue]] = []
    first = threading.Thread(target=lambda: said.append(posters.offer([_row()])))
    first.start()
    assert source.entered.wait(_SETTLE)
    second = threading.Thread(target=lambda: said.append(posters.urgent([_row()])))
    second.start()
    second.join(0.2)
    source.opened.set()
    first.join(_SETTLE)
    second.join(_SETTLE)
    assert len(source.judged) == 1, "одну картину судили дважды"
    assert [FIELD in one[0] for one in said if isinstance(one[0], dict)] == [True, True]


def test_an_empty_answer_under_429_is_asked_again_after_the_quiet(tmp_path: Path) -> None:
    """Пустой ответ в минуту 429 не держит картину пять минут: её спросят после тишины."""
    source, clock, storm = FakeSource(pages={}), _Clock(), _Storm(calm=119.0)
    posters = _posters(tmp_path, source, clock, storm)
    assert FIELD not in posters.urgent([_row()])[0]  # type: ignore[operator]
    assert posters.pending([_row()]) and not posters.due([_row()])
    posters.urgent([_row()])
    assert len(source.judged) == 1, "картину спросили снова до конца тишины"
    clock.now, storm.troubled = 119.0, False
    source.pages = {"Тачки": ["Cars"]}
    assert posters.due([_row()])
    assert FIELD in posters.urgent([_row()])[0]  # type: ignore[operator]
    assert len(source.judged) == 2


def test_a_source_down_for_long_is_asked_no_more_than_three_times(tmp_path: Path) -> None:
    """Источник, лежащий дольше трёх попыток, дальше держится обычным промахом."""
    source, clock, storm = FakeSource(pages={}), _Clock(), _Storm()
    posters = _posters(tmp_path, source, clock, storm)
    for _ in range(_ATTEMPTS + 2):
        storm.calm = clock.now
        posters.offer([_row()])
        clock.now += 1.0
    assert len(source.judged) == _ATTEMPTS
    assert not posters.pending([_row()])
    clock.now += _RETRY
    posters.offer([_row()])
    assert len(source.judged) == _ATTEMPTS + 1


def test_a_calm_empty_answer_is_a_miss_and_nothing_is_coming(tmp_path: Path) -> None:
    """Источник ответил без 429: картины нет, и страница не ждёт её дальше."""
    source, clock, storm = FakeSource(pages={}), _Clock(), _Storm(troubled=False)
    posters = _posters(tmp_path, source, clock, storm)
    posters.urgent([_row()])
    assert not posters.pending([_row()])
    clock.now += 10.0
    posters.urgent([_row()])
    assert len(source.judged) == 1


def test_a_picture_has_landed_only_once_its_bytes_are_here(tmp_path: Path) -> None:
    """Имя выдано по приговору, но плитка страницы получит его, когда байты лягут."""
    gate = threading.Event()
    source = FakeSource(gate=gate)
    posters = HitPosters(source, PosterShelf(home=lambda: tmp_path))
    assert FIELD in posters.urgent([_row()])[0]  # type: ignore[operator]
    assert not posters.landed(_row()) and posters.pending([_row()])
    gate.set()
    for _ in range(100):
        if posters.landed(_row()):
            break
        threading.Event().wait(0.02)
    assert posters.landed(_row()) and not posters.pending([_row()])
