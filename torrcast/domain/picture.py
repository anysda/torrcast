"""Правило Picture; используют модели и фасады разбора имён."""

from __future__ import annotations

from dataclasses import dataclass, field

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.kind import Kind
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify


@dataclass(slots=True)
class Picture:
    title: str
    year: int | None
    kind: Kind = "movie"
    original: str | None = None
    part: int | None = None
    also: str = ""
    aliases: tuple[str, ...] = ()
    releases: list[Release] = field(default_factory=list)
    native: bool = False
    #: Год, которым датированную соседку назвали нашим именем: её разобранный
    #: ``original`` совпал с нашим названием (:func:`torrcast.domain.anchor_years.anchor_years`).
    #: Только для порядка в меню (:attr:`sort_year`): сама картина года не получает.
    anchor: int | None = None

    @property
    def key(self) -> str:
        slug = slugify(self.title)
        if not self.year and self.original:
            slug = f"{slug}-{slugify(self.original)}"
        return f"{self.kind}:{slug}:{(self.year if self.year else '0')}"

    @property
    def franchise(self) -> str:
        return franchise_key(self.title)

    @property
    def sort_year(self) -> int | None:
        """Год для хронологии меню: свой, а у бесстрочной половины - привязанный."""
        return self.year if self.year is not None else self.anchor

    @property
    def rows(self) -> int:
        return sum(r.copies for r in self.releases)

    @property
    def collection(self) -> bool:
        return bool(self.releases) and all(r.collection for r in self.releases)

    @property
    def seeders(self) -> int:
        return max((r.seeders for r in self.releases), default=0)


__all__ = ["Picture"]
