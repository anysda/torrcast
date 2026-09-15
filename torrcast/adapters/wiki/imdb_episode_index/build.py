"""Сборка дискового индекса серий IMDb из выгрузки ``title.episode.tsv.gz``.

Выгрузка - девять миллионов строк «серия, сериал, сезон, номер». Индекс держит на
сериал и сезон одну строку номеров диапазонами («1-10,12»), и карточка читает сезоны
сериала одним запросом по tconst без сети (:mod:`.seasons`). Собирается установщиком
и затем раз в сутки службой (:mod:`.refresh`); выгрузка не менялась - не пересобирается.
"""

from __future__ import annotations

import gzip
import os
import sqlite3
import sys
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import IO
from urllib.request import urlopen

#: Чем открывается адрес выгрузки; тест подставляет свой файл.
Opener = Callable[[str], IO[bytes]]
#: Заголовки ответа, которые называют выгрузку: изменилась она - изменился и один из них.
_STAMP = ("ETag", "Last-Modified", "Content-Length")


def build(url: str, target: Path, opener: Opener | None = None) -> bool:
    """Собрать индекс, только если выгрузка изменилась; вернуть, была ли запись."""
    part = target.with_name(f"{target.name}.part")
    raw = target.with_name(f"{target.name}.raw")
    try:
        with (opener or _open)(url) as response:
            stamp = _stamp(response)
            if stamp and _current(target, stamp):
                return False
            for leftover in (part, raw):
                leftover.unlink(missing_ok=True)
            with gzip.open(response, "rt", encoding="utf-8", newline="\n") as lines:
                _collect(raw, lines)
        _write(raw, part, stamp)
        os.replace(part, target)
    except (OSError, EOFError, sqlite3.Error):
        part.unlink(missing_ok=True)
        return False
    finally:
        raw.unlink(missing_ok=True)
    return True


def _open(url: str) -> IO[bytes]:
    response: IO[bytes] = urlopen(url, timeout=60)
    return response


def _stamp(response: IO[bytes]) -> str:
    headers = getattr(response, "headers", None)
    return "\t".join(str(headers.get(name, "")) for name in _STAMP) if headers else ""


def _current(target: Path, stamp: str) -> bool:
    try:
        with sqlite3.connect(f"file:{target}?mode=ro", uri=True) as connection:
            values = dict(connection.execute("SELECT key, value FROM metadata"))
    except sqlite3.Error:
        return False
    return values.get("stamp") == stamp


def _collect(raw: Path, lines: Iterable[str]) -> None:
    """Сырые тройки во временный файл: сортирует их SQLite на диске, а не память."""
    connection = sqlite3.connect(raw)
    try:
        connection.executescript(
            "PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;"
            "CREATE TABLE raw (parent INTEGER, season INTEGER, number INTEGER);"
        )
        connection.executemany("INSERT INTO raw VALUES (?, ?, ?)", _triples(lines))
        connection.commit()
    finally:
        connection.close()


def _triples(lines: Iterable[str]) -> Iterator[tuple[int, int, int]]:
    for line in lines:
        fields = line.rstrip("\n").split("\t")
        if len(fields) < 4 or not fields[1].startswith("tt"):
            continue
        season, number = fields[2], fields[3]
        if season.isdigit() and number.isdigit():
            yield int(fields[1][2:]), int(season), int(number)


def _write(raw: Path, part: Path, stamp: str) -> None:
    part.unlink(missing_ok=True)
    connection = sqlite3.connect(part)
    try:
        connection.execute("ATTACH DATABASE ? AS source", (str(raw),))
        connection.executescript(
            """
            CREATE TABLE season (
                parent INTEGER NOT NULL,
                season INTEGER NOT NULL,
                numbers TEXT NOT NULL,
                PRIMARY KEY (parent, season)
            ) WITHOUT ROWID;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
            """
        )
        ordered = connection.execute(
            "SELECT DISTINCT parent, season, number FROM source.raw ORDER BY 1, 2, 3"
        )
        connection.executemany("INSERT INTO season VALUES (?, ?, ?)", _seasons(ordered))
        connection.execute("INSERT INTO metadata VALUES ('stamp', ?)", (stamp,))
        connection.commit()
    finally:
        connection.close()


def _seasons(ordered: Iterable[tuple[int, int, int]]) -> Iterator[tuple[int, int, str]]:
    """Сложить упорядоченные номера сезона в строку диапазонов."""
    key: tuple[int, int] | None = None
    spans: list[list[int]] = []
    for parent, season, number in ordered:
        if (parent, season) != key:
            if key is not None:
                yield (*key, _spans(spans))
            key, spans = (parent, season), []
        if spans and spans[-1][1] + 1 == number:
            spans[-1][1] = number
        else:
            spans.append([number, number])
    if key is not None:
        yield (*key, _spans(spans))


def _spans(spans: list[list[int]]) -> str:
    return ",".join(f"{low}-{high}" if high > low else str(low) for low, high in spans)


def _main() -> int:
    if len(sys.argv) != 3:
        return 2
    build(sys.argv[1], Path(sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["build"]
