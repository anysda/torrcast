"""Цифры приёмки: что приёмник увидел, забирая поток."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from torrcast.domain.catalogs.phrase import phrase

#: На сколько секунд декодеру разрешено не дотянуть до конца манифеста: недобор короче
#: этого числа приёмка засчитывает доигранным. Порог меньше сегмента сетки
#: (:attr:`torrcast.domain.profile.Profile.segment_seconds`, 10 с): недоигранным считается
#: только тот хвост, который не объясняется одним последним куском.
TAIL_SECONDS: Final = 8.0


@dataclass(slots=True)
class ReceptionReport:
    """Что приёмник увидел, забирая поток."""

    segments: int = 0
    duration: float = 0.0
    decoded: float = 0.0
    gaps: int = 0
    peak_mbit: float = 0.0
    #: Ответы без ``Access-Control-Allow-Origin``: Chromecast на таких молча молчит.
    no_cors: int = 0

    @property
    def ok(self) -> bool:
        """Приёмка: дыр нет, CORS везде, декодировано до конца (хвост в один сегмент)."""
        return (
            self.segments > 0
            and self.gaps == 0
            and self.no_cors == 0
            and self.decoded >= self.duration - TAIL_SECONDS
        )

    def line(self) -> str:
        """Цифры приёмки одной строкой."""
        return phrase(
            "receiver.reception",
            segments=self.segments,
            duration=f"{self.duration:.0f}",
            decoded=f"{self.decoded:.0f}",
            gaps=self.gaps,
            no_cors=self.no_cors,
            peak=f"{self.peak_mbit:.1f}",
        )
