"""Правило cluster; используют модели и фасады разбора имён."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain._name_data.data_1 import _CYRILLIC
from torrcast.domain.compose import _compose
from torrcast.domain.glue import glue
from torrcast.domain.kind import Kind
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
from torrcast.domain.sorted import _sorted
from torrcast.domain.unchaptered import _unchaptered


def cluster(
    releases: list[Release], *, glue_rule: Callable[[list[Picture]], list[Picture]] = glue
) -> list[Picture]:
    releases = sorted(releases, key=lambda r: (r.magnet, r.raw_name))
    aliases: dict[str, str] = {}
    paired: dict[tuple[Kind, str, int | None], set[str]] = {}
    original_kinds: dict[tuple[str, int | None], set[Kind]] = {}
    for release in releases:
        if release.original and _CYRILLIC.search(release.title):
            original = slugify(release.original)
            title = slugify(release.title)
            aliases.setdefault(original, title)
            paired.setdefault((release.kind, title, release.year), set()).add(original)
            original_kinds.setdefault((original, release.year), set()).add(release.kind)
    series_originals = {
        release.slug for release in releases if not release.original and release.kind == "tv"
    }
    disputed = {
        key
        for key, originals in paired.items()
        if len(originals) > 1 and any(len(x) == 1 for x in originals)
    }
    canon: dict[tuple[Kind, str, int | None], tuple[Kind, str, int | None]] = {}
    buckets: dict[tuple[Kind, str, int | None], list[Release]] = {}
    for release in releases:
        kind = release.kind
        slug = release.slug if release.original else aliases.get(release.slug, release.slug)
        if (
            not release.original
            and release.slug in series_originals
            and (len(kinds := original_kinds.get((release.slug, release.year), set())) == 1)
        ):
            kind = next(iter(kinds))
        key = (kind, slug, release.year)
        if release.original:
            original = slugify(release.original)
            if (release.kind, slugify(release.title), release.year) in disputed:
                key = (kind, original, release.year)
            else:
                key = canon.setdefault((kind, original, release.year), key)
        buckets.setdefault(key, []).append(release)
    pictures = [_compose(kind, year, group) for (kind, _, year), group in buckets.items()]
    return _sorted(_unchaptered(glue_rule(pictures)))


__all__ = ["cluster"]
