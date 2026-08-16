"""Ищет для сценариев сведения о фильме во внешних источниках."""

from typing import Protocol

from torrcast.domain.movie_facts import MovieFacts


class FactsSource(Protocol):
    def lookup(self, title: str, year: int | None = None) -> MovieFacts | None: ...
