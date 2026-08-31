"""Русский каталог кластера ``stream_pack``."""

from __future__ import annotations


def ru() -> dict[str, str]:
    return {
        "stream_pack.paused_from_remote": "пауза на пульте",
        "stream_pack.flag_write_failed": "флажок картинки не лёг ({flag}): {reason}",
        "stream_pack.stopped_ourselves": "сняли сами: {reason}",
        "stream_pack.killed_by_signal": "убит сигналом {signal}",
        "stream_pack.no_output": "нет вывода",
        "stream_pack.silent_with_code": "молча, код {code}",
    }
