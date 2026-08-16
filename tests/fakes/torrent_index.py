"""Возвращает тестам раздачи и запоминает запросы к каталогу."""

from dataclasses import dataclass, field

from torrcast.domain.release import Release


@dataclass
class FakeTorrentIndex:
    results: list[Release] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)

    def search(self, query: str) -> list[Release]:
        self.queries.append(query)
        return list(self.results)
