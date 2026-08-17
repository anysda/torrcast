"""Зеркало :mod:`torrcast.domain.trimmed_playlist`."""

from __future__ import annotations

import pytest

from torrcast.domain.trimmed_playlist import GRID_SLACK, trimmed_playlist

BASE = "http://127.0.0.1:9/hls"
#: Первый кусок дробный - ровно так его и отдаёт упаковщик, округляя ``EXTINF``.
SEGMENTS = [(f"v{slot}.ts", span) for slot, span in enumerate([10.023222, *[10.0] * 5])]


def test_the_head_is_cut_to_the_piece_the_entry_aims_at() -> None:
    """Декодеру отданы куски с нужного, адресами на ту же раздачу, а ``-ss`` - остаток."""
    cut = trimmed_playlist(SEGMENTS, BASE, 25.0)

    assert cut is not None
    text, offset = cut
    assert offset == pytest.approx(4.976778), "-ss остаётся остатком внутрь куска"
    lines = text.splitlines()
    assert [line for line in lines if not line.startswith("#")] == [
        f"{BASE}/v{slot}.ts" for slot in (2, 3, 4, 5)
    ]
    assert "#EXT-X-MEDIA-SEQUENCE:2" in lines, "нумерация продолжает манифест раздачи"
    assert "#EXT-X-ENDLIST" in lines and "#EXT-X-TARGETDURATION:11" in lines


def test_there_is_nothing_to_cut_inside_the_first_piece() -> None:
    """Заход в первый же кусок и так начинается с головы - резать нечего."""
    assert trimmed_playlist(SEGMENTS, BASE, 5.0) is None
    assert trimmed_playlist(SEGMENTS, BASE, 0.0) is None
    assert trimmed_playlist([], BASE, 25.0) is None


def test_an_entry_right_on_a_boundary_costs_no_seek_at_all() -> None:
    """Заход ровно на границу куска обходится без ``-ss``: кусок открывается с головы."""
    cut = trimmed_playlist(SEGMENTS, BASE, 40.023222)

    assert cut is not None
    text, offset = cut
    assert offset == 0.0
    ahead = [line for line in text.splitlines() if line.startswith("http")]
    assert ahead[0].endswith("/v4.ts"), "первым идёт кусок, в который целится заход"


def test_the_slack_keeps_the_boundary_from_slipping_a_piece_back() -> None:
    """Границы сетки складываются из округлённых ``EXTINF`` и на секунду захода не ложатся.

    Без допуска заход съезжал бы на кусок НАЗАД - то есть тащил бы за собой упаковку,
    ради чего голова плейлиста и срезается.
    """
    grid = [(f"v{slot}.ts", 10.0) for slot in range(6)]

    cut = trimmed_playlist(grid, BASE, 30.0 - GRID_SLACK / 2)

    assert cut is not None and "#EXT-X-MEDIA-SEQUENCE:3" in cut[0]
