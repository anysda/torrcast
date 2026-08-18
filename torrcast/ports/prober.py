"""Читает для сценариев паспорт медиапотока.

Спрашивается он у источника по адресу и всегда в срок: поток отдаёт живая раздача, и
ждать её ответа вечно показ не вправе. Кто отвечает - ffprobe или подделка стенда, -
решает композиционный корень (:mod:`torrcast.runtime.wire`).
"""

from collections.abc import Callable
from typing import Protocol

from torrcast.domain.media import Media


class Prober(Protocol):
    """Что сценариям нужно от чтения паспорта - и ничего сверх того."""

    def __call__(
        self,
        source_url: str,
        /,
        timeout: float = ...,
        alive: Callable[[], bool] | None = ...,
    ) -> Media:
        """Паспорт потока по адресу; ``timeout`` - сколько ждать ответа источника.

        ``alive`` - жив ли смысл дочитывать. Раздача с мёртвым роем метаданные отдаёт, а
        содержимого не отдаёт вовсе, и чтение молча сидит весь ``timeout``. Признак жизни
        (:func:`torrcast.adapters.stream_probe.swarm_pulse.swarm_pulse`) отличает такую от
        честно долгого заголовка; ``None`` - ждать по полному сроку.
        """
