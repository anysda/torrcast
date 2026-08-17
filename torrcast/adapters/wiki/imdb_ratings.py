"""Выгрузка оценок IMDb с диска; её читают добор справки и офлайн-карта имён."""

from __future__ import annotations

import threading
from pathlib import Path

from torrcast.domain.facts.imdb_rows import _scores, _vote_counts
from torrcast.domain.facts.settings import RATINGS_PATH
from torrcast.ports.text_source import TextSource


class ImdbRatings:
    """``tconst`` → рейтинг и число голосов из одного файла.

    Оценки читаются целиком один раз за запуск и только тогда, когда рейтинг кому-то
    понадобился: на пути показа его не трогают вовсе. С отсечкой по числу голосов,
    которую ставит `install.sh`, это ~2 МБ и сотня тысяч строк — чтение на глаз мгновенное.

    Голоса спрашиваются отдельно и только там, где на одно русское имя претендуют
    несколько картин, поэтому их разбор помнится на процесс.
    """

    def __init__(self, source: TextSource, path: Path = RATINGS_PATH) -> None:
        self.source = source
        self.path = path
        self._votes: dict[str, int] | None = None
        self._lock = threading.Lock()

    def scores(self) -> dict[str, str]:
        """``tconst`` → рейтинг. Нет файла — пустой словарь, и это не сбой."""
        return _scores(self.source.lines(self.path))

    def votes(self) -> dict[str, int]:
        """``tconst`` → число голосов; разбирается один раз на процесс."""
        with self._lock:
            if self._votes is None:
                self._votes = _vote_counts(self.source.lines(self.path))
            return self._votes
