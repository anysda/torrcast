"""Офлайн-карта русских прокатных имён IMDb - последний шаг справки, без сети."""

from __future__ import annotations

import threading
from pathlib import Path

from torrcast.domain.facts.imdb_rows import _named_origin, _ru_rows, _RuName
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import RU_NAMES_PATH
from torrcast.domain.slugify import slugify
from torrcast.ports.rating_dump import RatingDump
from torrcast.ports.text_source import TextSource


class ImdbNames:
    """Паспорт по прокатному имени: зовут, когда Википедия промолчала целиком.

    Русское прокатное имя картины без своей русской статьи живёт в выгрузке IMDb парой к
    оригиналу и году, и карта :data:`RU_NAMES_PATH` отвечает без сети.

    Файл - сотни тысяч строк: разбор это заметные доли секунды, поэтому читаем его только
    для картины, которой не нашлось в Википедии, а не на старте каждого `cast`. Нет файла
    (установка без справки, не скачалось) - пустая карта, и паспорт молчит ровно так, как
    молчал без неё.
    """

    def __init__(self, source: TextSource, ratings: RatingDump, path: Path = RU_NAMES_PATH) -> None:
        self.source = source
        self.ratings = ratings
        self.path = path
        self._names: dict[str, list[_RuName]] | None = None
        self._lock = threading.Lock()

    def look(self, title: str, series: bool) -> Origin:
        """Паспорт по офлайн-карте; чего в карте нет - о том молчим."""
        return _named_origin(self.names().get(slugify(title), []), series, self.ratings.votes)

    def names(self) -> dict[str, list[_RuName]]:
        """Карта русских прокатных имён. Читается один раз и лишь когда понадобилась."""
        with self._lock:
            if self._names is None:
                self._names = _ru_rows(self.source.lines(self.path))
            return self._names
