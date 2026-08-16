"""Facts about a movie returned by an external knowledge source."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MovieFacts:
    """Names, year and synopsis known about one picture."""

    title: str = ""
    original_title: str = ""
    year: int | None = None
    synopsis: str = ""
