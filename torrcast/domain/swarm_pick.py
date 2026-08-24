"""Приговор снабжению кандидата по окну его настоящего прогрева."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from torrcast.domain.swarm_supply import swarm_supply


def swarm_pick(
    samples: list[tuple[float, float]],
    file_index: int,
    file_size: int,
    duration: float,
    settle: float,
) -> tuple[float, float, float] | None:
    """Медианная доставка после разгона; ``None`` - честного окна не получилось."""
    window = [(elapsed, read) for elapsed, read in samples if elapsed >= settle]
    if len(window) < 2 or window[-1][0] <= window[0][0]:
        return None
    elapsed = window[-1][0] - window[0][0]
    speed = max(0.0, window[-1][1] - window[0][1]) / elapsed
    status: dict[str, JsonValue] = {
        "download_speed": speed,
        "file_stats": [{"id": file_index, "length": file_size}],
    }
    return swarm_supply(status, file_index, duration)
