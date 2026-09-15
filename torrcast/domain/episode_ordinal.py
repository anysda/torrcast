"""Серия строки каталога, когда раздачи нумеруют сериал иначе: по сквозному номеру.

IMDb держит «Интернов» четырьмя сезонами (60, 60, 61, 98), раздачи - четырнадцатью по 20.
Строка s3e20 такого списка - 140-я серия сериала, и в паке «1-14 сезоны» это s7e20 «(140)»,
а не s3e20 «(060)». Сквозной номер считается по числу серий сезонов показанного списка,
как Torrentio раскладывает сквозные номера файлов по сезонам Cinemeta:

1. номер каждого файла больше числа серий его сезона в списке или файлы - кусок первого
   сезона не с первой серии - номера сквозные, и серия N - файл с номером N («Ван-Пис 1061»);
2. иначе серия N - N-й файл подряд от s1e1 по сезонам и сериям без пропусков;
3. иначе серии не найти: пропуск или пак не с первого сезона - честный отказ, а не соседняя.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import count
from typing import Final

from torrcast.domain.episode import Episode
from torrcast.domain.episode_file import EpisodeFile

#: Число серий сезонов 1..N через запятую, как его несёт ``--layout``: «60,60,61,98».
_COUNTS: Final = re.compile(r"[1-9]\d{0,4}(?:,[1-9]\d{0,4}){0,199}")


@dataclass(frozen=True, slots=True)
class EpisodeOrdinal:
    """Числа серий сезонов 1..N показанного списка."""

    counts: tuple[int, ...]

    @classmethod
    def read(cls, text: str) -> EpisodeOrdinal | None:
        """Числа из ``--layout``; неразборчивое - ``None``."""
        if not _COUNTS.fullmatch(text):
            return None
        return cls(tuple(int(part) for part in text.split(",")))

    def want(self, asked: Episode) -> Episode | None:
        """Серия списка как сквозной номер ``s1eN``; вне списка - ``None``."""
        season, episode, counts = asked.season, asked.episode, self.counts
        if not 1 <= season <= len(counts) or not 1 <= episode <= counts[season - 1]:
            return None
        return Episode(1, sum(counts[: season - 1]) + episode)

    def find(self, files: Sequence[EpisodeFile], ordinal: int) -> EpisodeFile | None:
        """Файл сквозной серии ``ordinal`` среди разобранных файлов раздачи или ``None``."""
        numbered = [file for file in files if file.season >= 1]
        beyond = all(0 < self._held(f.season) < f.episode for f in numbered)
        chunk = {f.season for f in numbered} == {1} and min(f.episode for f in numbered) > 1
        if numbered and (beyond or chunk):
            return next((file for file in numbered if file.episode == ordinal), None)
        seasons: dict[int, dict[int, EpisodeFile]] = {}
        for file in numbered:
            seasons.setdefault(file.season, {}).setdefault(file.episode, file)
        before = 0
        for season in count(1):
            numbers = seasons.get(season)
            if numbers is None:
                return None
            run = next(n for n in count(1) if n not in numbers) - 1
            if ordinal <= before + run:
                return numbers[ordinal - before]
            if run != len(numbers):
                return None
            before += run
        return None

    def _held(self, season: int) -> int:
        return self.counts[season - 1] if season <= len(self.counts) else 0


__all__ = ["EpisodeOrdinal"]
