"""Слот по имени файла: своё имя разбирается, чужое отвечает ``-1``, а не догадкой."""

from __future__ import annotations

import pytest

from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.adapters.stream_probe.segment_slot import segment_slot


@pytest.mark.parametrize("slot", [0, 7, 359, 1000])
def test_the_name_and_the_slot_are_the_same_thing_read_both_ways(slot: int) -> None:
    """Уборка позади показа и раздача наружу читают одно и то же имя."""
    assert segment_slot(segment_name(slot)) == slot


@pytest.mark.parametrize(
    "name",
    ["index.m3u8", "v.ts", "vX.ts", "v1.mp4", "pack/v1.ts", "v1.ts.tmp", "", "v-1.ts"],
)
def test_a_name_that_is_not_ours_is_answered_by_minus_one(name: str) -> None:
    """Чужой файл в каталоге показа не должен превратиться в чей-то слот сетки."""
    assert segment_slot(name) == -1
