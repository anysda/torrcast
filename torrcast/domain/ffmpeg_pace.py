"""Что считается честным ffmpeg-темпом: секунды, вокруг которых меряет самопроверка.

Числа те же, что и в ``install.sh`` (``FFMPEG_PACE_*`` там, TC-1048): порог назван не
на глаз, а измерением на четырёх настоящих сборках (6.1.1, 7.1.4, 7.1.5 - честные,
8.0.1 - burst инертен и темп считается от начала файла, а не от места входа). Запас
(``PACE_MARGIN_SECONDS`` сверх базовой линии при готовых 0.02-0.13 с у честных сборок)
на порядок шире дрожания живой машины.
"""

from __future__ import annotations

from dataclasses import dataclass

#: с; столько просим прочитать при включённом burst.
PACE_BURST_SECONDS = 8.0
#: с; куда садимся -ss при -copyts.
PACE_ENTRY_SECONDS = 10.0
#: с; сколько читаем после посадки.
PACE_ENTRY_READ_SECONDS = 3.0
#: с; допуск сверх базовой линии без темпа вовсе.
PACE_MARGIN_SECONDS = 3.0
#: с; потолок каждого живого прогона - инертная/путающая сборка всё равно его достаёт.
PACE_DEADLINE_SECONDS = 5.0


@dataclass(frozen=True)
class FfmpegPace:
    """Секунды трёх живых прогонов: без темпа, с burst'ом и с посадкой вглубь файла."""

    baseline_seconds: float
    burst_seconds: float
    entry_seconds: float

    @property
    def burst_honored(self) -> bool:
        """Правда ли ``-readrate_initial_burst`` не инертен: burst не дороже базовой линии."""
        return self.burst_seconds <= self.baseline_seconds + PACE_MARGIN_SECONDS

    @property
    def entry_paced(self) -> bool:
        """Правда ли темп считается от места входа, а не от начала файла."""
        return self.entry_seconds <= self.baseline_seconds + PACE_MARGIN_SECONDS
