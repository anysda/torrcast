"""Достаточность фактической доставки исходного файла из роя."""

from __future__ import annotations

import math
from collections.abc import Mapping

from torrcast.domain.json_value import JsonValue

ENOUGH = 1.0


def swarm_supply(
    status: Mapping[str, JsonValue], file_index: int, duration: float
) -> tuple[float, float, float] | None:
    """Вернуть ``(доля реального времени, приехало Мбит/с, нужно Мбит/с)``.

    ``download_speed`` - скорость, с которой служба получает байты исходной раздачи.
    Нужная скорость - размер выбранного файла, делённый на его длительность. Поэтому
    единица означает ровно одну секунду исходника за секунду стены. Поля полки HLS и
    отдачи приёмнику здесь намеренно не участвуют: это другие участки тракта.
    """
    speed = status.get("download_speed")
    files = status.get("file_stats")
    if not isinstance(speed, (int, float)) or isinstance(speed, bool):
        return None
    if not math.isfinite(speed) or speed < 0:
        return None
    if not isinstance(files, list) or duration <= 0:
        return None
    for raw in files:
        if not isinstance(raw, dict) or raw.get("id") != file_index:
            continue
        size = raw.get("length")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            return None
        need = size / duration
        return speed / need, speed * 8 / 1_000_000, need * 8 / 1_000_000
    return None
