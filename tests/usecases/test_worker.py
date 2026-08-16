"""Зеркально проверяет точку входа показа внутри юнита."""

from torrcast.usecases.worker import _cmd_worker


def test_worker_entry_point_is_importable() -> None:
    assert _cmd_worker is not None
