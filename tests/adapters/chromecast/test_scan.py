"""Проверяет прежний путь к адаптеру сетевого поиска."""

import torrcast.scan as facade
from torrcast.adapters.chromecast import scan


def test_facade_points_to_adapter() -> None:
    assert facade is scan
