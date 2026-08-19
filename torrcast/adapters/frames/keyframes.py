"""Карта опорных кадров раздачи: индекс контейнера диапазонными запросами."""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from torrcast.adapters.frames.http_range_reader import HttpRangeReader
from torrcast.domain.frames.keymap.key_map import KeyMap
from torrcast.domain.frames.range_reader import RangeReader
from torrcast.domain.infra_error import InfraError

#: Сколько головы берём первым запросом. Кусок мал нарочно: у холодной раздачи каждый
#: лишний мегабайт - это секунды старта, а по этим байтам нужно всего лишь узнать
#: контейнер и место индекса. Не хватило - разбор дочитывает голову целиком
#: (:data:`torrcast.domain.frames.mkv.HEAD_BYTES`), а не тянет файл.
HEAD_PEEK: Final = 256 << 10

#: Чем берутся байты по адресу: боевой HTTP-читатель или подделка стенда.
Source = Callable[[str], RangeReader]


def keyframes(url: str, *, source: Source = HttpRangeReader, head_peek: int = HEAD_PEEK) -> KeyMap:
    """Читает индекс контейнера диапазонными HTTP-запросами.

    ``source`` - чем брать байты, ``head_peek`` - сколько взять первым куском. Оба с
    боевым умолчанием: продукт зовёт с одним доводом, а стенд подсовывает файл с диска
    и маленькую голову, чтобы проверить дочитывание.
    """
    reader = source(url)
    head = reader.read(0, head_peek)
    if head[:4] == b"\x1a\x45\xdf\xa3":
        from torrcast.domain.frames.mkv.keys import keys

        return keys(reader, head)
    if head[4:8] in {b"ftyp", b"moov", b"free", b"skip", b"mdat", b"wide"}:
        from torrcast.domain.frames.mp4.keys import keys

        return keys(reader, head)
    raise InfraError("это не mkv и не mp4: карту опорных кадров взять неоткуда")
