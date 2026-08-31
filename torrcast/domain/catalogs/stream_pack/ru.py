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
        "stream_pack.merge_failed": "склейка не вышла",
        "stream_pack.merge_not_seated": "склейку не поставить на ленту показа",
        "stream_pack.astray_both": "склейка не с этого места целиком",
        "stream_pack.astray_picture": "картинка склейки не с этого места",
        "stream_pack.astray_sound": "звук склейки не с этого места",
    }
