"""Возвращает тестам паспорт медиа и запоминает источник."""

from dataclasses import dataclass, field

from torrcast.domain.media import Media


@dataclass
class FakeProber:
    result: Media
    sources: list[str] = field(default_factory=list)

    def probe(self, source_url: str) -> Media:
        self.sources.append(source_url)
        return self.result
