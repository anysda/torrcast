"""Системная среда сценария прогрева."""

import shutil
import time
from importlib import import_module
from typing import Any


class _SystemWarmEnvironment:
    """Связывает порт прогрева с часами, диском и телеметрией."""

    epoch = staticmethod(time.time)
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)

    @staticmethod
    def remove_tree(path: Any) -> None:
        shutil.rmtree(path, ignore_errors=True)

    @staticmethod
    def emit(event: str, *args: object, **facts: object) -> None:
        getattr(import_module("torrcast.trace"), event)(*args, **facts)

    @staticmethod
    def mark(name: str, **facts: object) -> None:
        import_module("torrcast.timing").mark(name, **facts)


environment = _SystemWarmEnvironment()
