"""Проверяет прежний путь к внешней части медиатракта."""

import torrcast.stream_serve as facade
from torrcast.adapters.http_server import stream_serve


def test_facade_points_to_adapter() -> None:
    assert facade is stream_serve
