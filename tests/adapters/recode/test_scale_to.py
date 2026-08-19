"""Фильтр ужатия кадра: габарит ступени, ни пикселя вверх и чётные стороны."""

from __future__ import annotations

from torrcast.adapters.recode.scale_to import scale_to


def test_the_frame_is_shrunk_by_its_box_and_never_stretched_up() -> None:
    """Скоуп 3840×1600 - тот же 2160p, и по одной высоте он ушёл бы ШИРЕ 1080p."""
    chain = scale_to(1080)

    assert "w=min(iw\\,1920)" in chain and "h=min(ih\\,1080)" in chain
    assert "force_original_aspect_ratio=decrease" in chain, "габарит ужат до пропорций входа"
    assert "force_divisible_by=2" in chain, "нечётная сторона кодировщику не даётся"
