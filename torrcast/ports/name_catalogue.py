"""Отвечает паспортом по офлайн-карте прокатных имён; зовёт сценарий паспорта."""

from typing import Protocol

from torrcast.domain.facts.origin import Origin


class NameCatalogue(Protocol):
    """Последний шаг справки: сети тут нет, есть чтение выгрузки."""

    def look(self, title: str, series: bool) -> Origin: ...
