"""Проверки глубины цвета."""

from torrcast.domain.color_depth import color_depth


def test_depth_from_pixel_format() -> None:
    assert color_depth("yuv420p10le") == 10
