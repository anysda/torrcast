"""Отвечает, где в mkv лежит индекс ``Cues``; спрашивает прогрев продолжения с середины."""

from __future__ import annotations

from torrcast.adapters.frames.http_range_reader import HttpRangeReader
from torrcast.adapters.frames.keyframes import HEAD_PEEK, Source
from torrcast.domain.frames.mkv.head import Head


def cues_at(source_url: str, *, source: Source = HttpRangeReader) -> int | None:
    """Смещение ``Cues`` по голове файла; ``None`` - голова его не называет.

    Голову к этому времени прогрев уже протянул, и 256 КБ берутся из кэша TorrServer.
    Дочитывать 4 МБ, как разбор карты, тут незачем: не назвала малая голова - прогрев
    просто обходится без индекса. ``source`` - чем брать байты: стенд читает файл с диска.
    """
    return Head(source(source_url).read(0, HEAD_PEEK)).cues_at
