"""Проверяет прежний путь к адаптеру приёмника."""

import torrcast.cast as facade
from torrcast.adapters.chromecast import cast


def test_facade_points_to_adapter() -> None:
    assert facade is cast
