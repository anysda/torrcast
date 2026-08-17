"""Читает для сценариев паспорт медиапотока.

Спрашивается он у источника по адресу и всегда в срок: поток отдаёт живая раздача, и
ждать её ответа вечно показ не вправе. Кто отвечает - ffprobe или подделка стенда, -
решает композиционный корень (:mod:`torrcast.runtime.wire`).
"""

from typing import Protocol

from torrcast.domain.media import Media


class Prober(Protocol):
    """Что сценариям нужно от чтения паспорта - и ничего сверх того."""

    def __call__(self, source_url: str, /, timeout: float = ...) -> Media:
        """Паспорт потока по адресу; ``timeout`` - сколько ждать ответа источника."""
