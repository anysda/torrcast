"""Офлайн-карта русских прокатных имён IMDb - последний шаг справки, без сети."""

from __future__ import annotations

import threading
from pathlib import Path

from torrcast.domain.facts.imdb_rows import (
    _TV_KINDS,
    _named_origin,
    _picture_ids_from_lines,
    _rows_by_name,
    _rows_by_year,
    _ru_rows,
    _RuName,
)
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
        self._years: dict[str, list[str]] | None = None
        self._named: dict[str, dict[str, list[str]]] = {}
        self._originals: dict[str, dict[str, list[str]]] = {}
        self._rows_lock = threading.Lock()
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

    def ids(self, pictures: list[tuple[str, int | None, str]]) -> dict[tuple[str, int | None], str]:
        """IMDb-id по точной тройке «прокатное имя, год, тип».

        Файл читается раз на процесс и раскладывается по годам; имена сводятся лишь в
        спрошенном году. Сверку делает всё тот же :func:`_picture_ids_from_lines`.
        """
        rows: dict[str, None] = {}
        for title, year, _kind in pictures:
            if year is not None:
                rows.update(dict.fromkeys(self._year(str(year)).get(slugify(title), ())))
        return _picture_ids_from_lines(rows, pictures)

    def ru_names(
        self, pictures: list[tuple[str, int | None, str]]
    ) -> dict[tuple[str, int | None], list[str]]:
        """Прокатные имена по оригиналу, году и типу: «Avatar» 2009 - это «Аватар».

        Поиск Википедии по латинскому имени приносит соседние части франшизы, а статья
        самой картины лежит под русским именем, которое знает карта.
        """
        out: dict[tuple[str, int | None], list[str]] = {}
        for key, name, _tconst in self._originals_of(pictures):
            if name not in out.setdefault(key, []):
                out[key].append(name)
        return out

    def original_ids(
        self, pictures: list[tuple[str, int | None, str]]
    ) -> dict[tuple[str, int | None], list[str]]:
        """IMDb-id картины по оригиналу, году и типу: «Lioness» 2023 - это tt13111078.

        Прокатное имя приводит к статье, которая называет другой оригинал: IMDb переименовал
        сериал, а статья «Спецназ: Львица» помнит «Special Ops: Lioness». Одну картину в них
        доказывает id, а не совпадение имён.
        """
        out: dict[tuple[str, int | None], list[str]] = {}
        for key, _name, tconst in self._originals_of(pictures):
            if tconst and tconst not in out.setdefault(key, []):
                out[key].append(tconst)
        return out

    def _originals_of(
        self, pictures: list[tuple[str, int | None, str]]
    ) -> list[tuple[tuple[str, int | None], str, str]]:
        """Строки карты под оригиналом того же года и типа: ключ, прокатное имя, IMDb-id."""
        rows: list[tuple[tuple[str, int | None], str, str]] = []
        for title, year, kind in pictures:
            if year is None:
                continue
            for line in self._year(str(year), originals=True).get(slugify(title), ()):
                name, tconst, imdb_kind = [*line.split("\t"), "", ""][:3]
                if (imdb_kind in _TV_KINDS) == (kind == "tv") and name:
                    rows.append(((title, year), name, tconst))
        return rows

    def _year(self, year: str, originals: bool = False) -> dict[str, list[str]]:
        """Строки одного года по сведённому имени; разбираются при первом вопросе."""
        with self._rows_lock:
            if self._years is None:
                self._years = _rows_by_year(self.source.lines(self.path))
            named = self._originals if originals else self._named
            if year not in named:
                named[year] = _rows_by_name(self._years.get(year, ()), 3 if originals else 0)
            return named[year]
