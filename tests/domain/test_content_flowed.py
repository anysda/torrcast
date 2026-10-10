"""Зеркало правила content_flowed: содержимое считается по полезным счётчикам, не по протоколу."""

from __future__ import annotations

import pytest

from torrcast.domain.content_flowed import content_flowed


@pytest.mark.parametrize(
    "status",
    [{"bytes_read_useful_data": 16384}, {"chunks_read_useful": 1, "bytes_read_useful_data": 0}],
)
def test_useful_content_counted_by_the_service_is_content(status: dict[str, int]) -> None:
    """Служба сама заказала блок и получила его - рой отдаёт содержимое."""
    assert content_flowed(status) is True


@pytest.mark.parametrize(
    "status",
    [
        {},
        {"active_peers": 3, "bytes_read": 90_000, "bytes_read_data": 0},
        {"bytes_read_useful_data": 0, "chunks_read_useful": 0},
        {"bytes_read_useful_data": True},
    ],
)
def test_talk_without_content_is_not_content(status: dict[str, object]) -> None:
    """🔴 TC-1420. Пир шлёт метаданные и служебное, а содержимого нет - это не «отдаёт»."""
    assert content_flowed(status) is False  # type: ignore[arg-type]
