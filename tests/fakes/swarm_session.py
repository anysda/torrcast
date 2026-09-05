"""Служба раздач, отвечающая ПО СЦЕНАРИЮ сеанса: замер за замером, последний - навсегда.

Последний повторяется не для удобства: после того как показ сдался, тянуть перестали, и
служба показывает ту же упавшую скорость на каждый следующий вопрос - в том числе на все
посмертные (:data:`torrcast.domain.revive_settings.SOURCE_TRIES`).
"""

from __future__ import annotations

#: Длительность и размер выбраны так, чтобы нужная скорость вышла ровно 17.81 Мбит/с - как
#: в следе стенда `.136` за 03-09-2026, на котором снят приговор здоровому рою.
SESSION_DUR = 2000.0
SESSION_SIZE = int(17.81 * 1_000_000 / 8 * SESSION_DUR)
#: Дословная жалоба на просевший рой из того же следа.
THIN_SWARM = (
    "the swarm delivers 0.20 Mbit/s against the needed 17.81 Mbit/s - supply is short (0.01x)"
)


class SwarmSession:
    """Скорости сеанса в Мбит/с: сколько назвали, столько замеров и будет разными."""

    def __init__(self, mbits: list[float]) -> None:
        self.mbits, self.asked = mbits, 0

    def alive(self) -> bool:
        return True

    def listed(self, torrent_hash: str) -> bool:
        return True

    def status(self, torrent_hash: str) -> dict[str, object]:
        mbit = self.mbits[min(self.asked, len(self.mbits) - 1)]
        self.asked += 1
        return {
            "download_speed": mbit * 1_000_000 / 8,
            "file_stats": [
                {"id": 0, "path": "s01e01.mkv", "length": SESSION_SIZE},
                {"id": 1, "path": "s01e02.mkv", "length": SESSION_SIZE},
            ],
        }

    def add(self, magnet: str) -> str:
        return "hash"
