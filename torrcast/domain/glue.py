"""Правило glue; используют модели и фасады разбора имён."""

from __future__ import annotations

import re

from torrcast.domain._name_data import _ALTERNATIVE_PICTURE_RE, _ALTERNATIVE_TITLE_RE, _ROMAN
from torrcast.domain.compose import _compose
from torrcast.domain.glued_year import _glued_year
from torrcast.domain.in_digits import in_digits
from torrcast.domain.kind import Kind
from torrcast.domain.link import _link
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify


def glue(pictures: list[Picture]) -> list[Picture]:
    parent = list(range(len(pictures)))

    def identity(name: str) -> str:
        plain = re.sub("(?:-)?(?:в-)?3[дd]$", "", slugify(name)).rstrip("-")
        return re.sub(
            "(?<=-)(?:часть|part)-([ivx]{1,4})$",
            lambda match: (
                match.group(0)[: match.group(0).rfind("-") + 1]
                + str(_ROMAN.get(match.group(1), match.group(1)))
            ),
            plain,
        )

    def alternative_release(release: Release) -> bool:
        title = release.raw_name.split(" / ", 1)[0]
        return bool(
            _ALTERNATIVE_PICTURE_RE.search(release.raw_name) or _ALTERNATIVE_TITLE_RE.search(title)
        )

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = (root(a), root(b))
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    alternative = [
        bool(p.releases) and all(alternative_release(r) for r in p.releases) for p in pictures
    ]
    disputed = {
        (picture.kind, slugify(picture.title), picture.year)
        for picture in pictures
        if picture.original
        and len(
            {
                slugify(other.original)
                for other in pictures
                if other.original
                and other.kind == picture.kind
                and (other.year == picture.year)
                and (slugify(other.title) == slugify(picture.title))
            }
        )
        > 1
        and any(
            len(slugify(other.original)) == 1
            for other in pictures
            if other.original
            and other.kind == picture.kind
            and (other.year == picture.year)
            and (slugify(other.title) == slugify(picture.title))
        )
    }
    named: dict[tuple[Kind, str, bool], list[int]] = {}
    for i, picture in enumerate(pictures):
        title = identity(picture.title)
        contested = (picture.kind, title, picture.year) in disputed
        names = set() if contested else {title}
        if picture.original:
            names.add(identity(picture.original))
        if not contested:
            names |= {in_digits(name) for name in names if name}
        for name in names:
            if name:
                named.setdefault((picture.kind, name, alternative[i]), []).append(i)
    for same in named.values():
        _link(pictures, same, union)
    lone: dict[tuple[Kind, str, bool], list[int]] = {}
    for i, picture in enumerate(pictures):
        if picture.original:
            continue
        for name in {(slug := identity(picture.title)), in_digits(slug)}:
            if name:
                lone.setdefault((picture.kind, name, alternative[i]), []).append(i)
    for i, picture in enumerate(pictures):
        for alias in picture.aliases:
            for name in (alias, in_digits(alias)):
                if (
                    bucket := lone.get((picture.kind, name, alternative[i]))
                ) is not None and i not in bucket:
                    bucket.append(i)
    for same in lone.values():
        _link(pictures, same, union)
    groups: dict[int, list[int]] = {}
    for i in range(len(pictures)):
        groups.setdefault(root(i), []).append(i)
    out: list[Picture] = []
    for members in groups.values():
        if len(members) == 1:
            out.append(pictures[members[0]])
            continue
        merged = sorted(
            (pictures[i] for i in members),
            key=lambda p: (-len(p.releases), p.title, p.original or ""),
        )
        releases = [r for p in merged for r in p.releases]
        year = _glued_year(merged[0].kind, merged, releases)
        fresh = _compose(merged[0].kind, year, releases)
        fresh.also = next((p.title for p in merged if slugify(p.title) != slugify(fresh.title)), "")
        out.append(fresh)
    return out


__all__ = ["glue"]
