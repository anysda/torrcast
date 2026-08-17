# mypy: disable-error-code=no-any-return
"""Системная среда сценария прогрева."""

import shutil
import time
from importlib import import_module
from typing import Any

from torrcast.ports.journal import journal


class _LazyPacker:
    """Откладывает импорт упаковщика до настоящего запуска прогрева."""

    @classmethod
    def start(cls, *args: object, **kwargs: object) -> object:
        return import_module("torrcast.stream").Packer.start(*args, **kwargs)


class _SystemWarmEnvironment:
    """Связывает порт прогрева с часами, диском и телеметрией."""

    epoch = staticmethod(time.time)
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)

    @staticmethod
    def segment_name(slot: int) -> str:
        return import_module("torrcast.stream").segment_name(slot)

    @staticmethod
    def segment_slot(name: str) -> int:
        return import_module("torrcast.stream").segment_slot(name)

    @staticmethod
    def hms(seconds: float) -> str:
        return import_module("torrcast.cli")._hms(seconds)

    @property
    def packer_type(self) -> object:
        return _LazyPacker

    @staticmethod
    def pack_command(*args: object, **kwargs: object) -> object:
        return import_module("torrcast.stream").ffmpeg_pack_command(*args, **kwargs)

    @staticmethod
    def pack_start(*args: object, **kwargs: object) -> object:
        return import_module("torrcast.stream").pack_start(*args, **kwargs)

    audio_mbit = 0.192
    max_segment_bytes = 16_000_000
    ts_overhead = 1.03

    @staticmethod
    def remove_tree(path: Any) -> None:
        shutil.rmtree(path, ignore_errors=True)

    @staticmethod
    def emit(event: str, *args: object, **facts: object) -> None:
        getattr(import_module("torrcast.trace"), event)(*args, **facts)

    @staticmethod
    def mark(name: str, **facts: object) -> None:
        journal().mark(name, **facts)


environment = _SystemWarmEnvironment()
