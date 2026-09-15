"""Зеркало :meth:`hass.hit_posters.HitPosters._land`: байты не доехали - это не промах.

Приговор уже назвал адрес постера, и обрыв на байтах значит «источник промолчал», а не
«картинки нет». На стенде обрыв чтения у IMDb прятал три обложки «Оно» из двенадцати на
:data:`~hass.hit_claims._RETRY`: страница переставала ждать через 17 с и так и оставалась без них.
"""

from __future__ import annotations

import time
from pathlib import Path

from hass.hit_ask import _about, _name
from hass.hit_claims import _ATTEMPTS
from hass.hit_posters import FIELD, HitPosters
from tests.test_hit_posters import _SETTLE, POSTER, FakeSource, _hits, _row
from torrcast.domain.json_value import JsonValue


def _settle(hits: HitPosters, records: list[JsonValue]) -> None:
    """Дождаться, пока байты записей перестанут быть в пути."""
    names = [_name(ask) for ask in map(_about, records) if ask is not None]
    deadline = time.monotonic() + _SETTLE
    while time.monotonic() < deadline and any(name in hits._pending for name in names):
        time.sleep(0.01)


def test_a_poster_whose_bytes_timed_out_is_asked_again_and_lands(tmp_path: Path) -> None:
    source = FakeSource(body=None)
    hits = _hits(tmp_path, source, now=lambda: 0.0)
    rows: list[JsonValue] = [_row()]
    hits.offer(rows)
    _settle(hits, rows)
    assert hits.pending(rows), "обрыв байтов после приговора записан промахом на пять минут"
    assert hits.due(rows), "обрыв байтов не спрашивается снова"

    source.body = POSTER
    again = hits.offer(rows)[0]
    _settle(hits, rows)
    assert isinstance(again, dict) and FIELD in again, f"повтор не дал имени: {again}"
    assert hits.landed(again), "повтор не положил байты"


def test_a_source_that_never_gives_bytes_stops_after_the_attempts(tmp_path: Path) -> None:
    source = FakeSource(body=None)
    hits = _hits(tmp_path, source, now=lambda: 0.0)
    rows: list[JsonValue] = [_row()]
    for _ in range(_ATTEMPTS):
        hits.offer(rows)
        _settle(hits, rows)
    assert not hits.pending(rows), "молчащий источник байтов спрашивается без конца"
    assert len(source.loaded) == _ATTEMPTS, f"походов за байтами: {len(source.loaded)}"
