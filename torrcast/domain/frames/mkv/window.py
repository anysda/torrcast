"""Окно у индекса: Cues и кластеры перед ними одним заходом к рою.

Пара проб у индекса (:func:`~torrcast.domain.frames.mkv.probes.probes`) берётся из
кластеров в 0.2-1.1 МБ перед ``Cues``, а каждая проба - это свой запрос. Замер холодных
показов 10-10: эти три-четыре захода шли друг за другом по 1-1.5 с и добавляли к старту
около 4 с. Рою же всё равно, сколько байтов отдать из места, которое он и так поднимает
под индекс: дорог заход, а не мегабайт. Поэтому индекс читается вместе с хвостом перед
ним, и пробы у индекса отвечают из памяти.
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.frames.range_reader import RangeReader as Reader

#: Сколько файла перед ``Cues`` берём тем же запросом. Пара проб лежит в 0.2-1.1 МБ перед
#: индексом, и кластер её кончается не дальше самого индекса; запас - на толстый кластер.
BEFORE: Final = 2 << 20


class Window:
    """Читатель, который отвечает из уже прочитанного окна и ходит к рою только мимо него."""

    def __init__(self, reader: Reader, at: int, size: int, before: int = BEFORE) -> None:
        self._reader = reader
        self.start = max(0, at - before)
        self.data = reader.read(self.start, at + size - self.start)
        # Отдали меньше, чем просили, - окно упёрлось в конец файла, и дальше читать нечего.
        self._eof = len(self.data) < at + size - self.start

    # Цену ведёт сам рой: окно лишь не ходит к нему лишний раз.
    @property
    def taken(self) -> int:
        return self._reader.taken

    @taken.setter
    def taken(self, value: int) -> None:
        self._reader.taken = value

    @property
    def requests(self) -> int:
        return self._reader.requests

    @requests.setter
    def requests(self, value: int) -> None:
        self._reader.requests = value

    def tail(self, at: int) -> bytes:
        """Байты окна с адреса ``at`` до его конца."""
        return self.data[at - self.start :]

    def read(self, offset: int, size: int) -> bytes:
        end = self.start + len(self.data)
        if self.start <= offset and (offset + size <= end or self._eof):
            return self.data[offset - self.start : offset - self.start + size]
        return self._reader.read(offset, size)
