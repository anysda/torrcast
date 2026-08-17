"""Фасад карты опорных кадров: прежние имена ведут в новые дома, а не в копию.

Сама карта проверяется там, где она снимается: ``tests/adapters/frames/test_keyframes``
и ``tests/domain/frames``. Здесь остаётся то, ради чего фасад и существует, - имена, по
которым его зовут щупы и прежние импорты.
"""

from __future__ import annotations

from torrcast import keymap
from torrcast.adapters.frames import keyframes as home
from torrcast.adapters.frames.http_range_reader import HttpRangeReader
from torrcast.domain.frames import keymap as rules


def test_every_exported_name_is_the_one_from_its_home() -> None:
    """Фасад отдаёт те же объекты, а не свои копии: подмена в тестах обязана долетать."""
    assert keymap.keyframes is home.keyframes
    assert keymap.HEAD_PEEK == home.HEAD_PEEK
    assert keymap.Reader is HttpRangeReader
    assert keymap.KeyMap is rules.KeyMap
    assert keymap.Point is rules.Point
    assert keymap.video_track is rules.video_track


def test_the_facade_promises_exactly_what_it_has() -> None:
    """Обещанное в ``__all__`` и вправду отсюда берётся."""
    assert sorted(keymap.__all__) == keymap.__all__
    assert all(hasattr(keymap, name) for name in keymap.__all__)
