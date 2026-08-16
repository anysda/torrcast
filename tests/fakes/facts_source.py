"""Возвращает тестам сведения о фильме и запоминает запросы."""

from dataclasses import dataclass, field

from torrcast.domain.movie_facts import MovieFacts


@dataclass
class FakeFactsSource:
    result: MovieFacts | None = None
    lookups: list[tuple[str, int | None]] = field(default_factory=list)

    def lookup(self, title: str, year: int | None = None) -> MovieFacts | None:
        self.lookups.append((title, year))
        return self.result
