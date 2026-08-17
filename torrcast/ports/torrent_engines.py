"""Заводит для сценариев клиента службы раздач по её адресу.

Адрес и срок ответа знает сценарий: короткий срок сторожа отличает мёртвую службу от
живой сразу, а показу нужен обычный. А ЧЕМ заводить - не его дело, и приходит это от
композиционного корня (:mod:`torrcast.runtime.wire`).
"""

from typing import Protocol

from torrcast.ports.torrent_engine import TorrentEngine


class TorrentEngines(Protocol):
    """Что сценариям нужно от завода службы раздач - и ничего сверх того."""

    def __call__(self, base_url: str, timeout: float = ...) -> TorrentEngine:
        """Клиент службы по адресу ``base_url``; ``timeout`` - сколько ждать её ответа."""
