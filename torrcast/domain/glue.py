"""Правило glue; используют модели и фасады разбора имён."""

from __future__ import annotations

import re

from torrcast.domain._name_data.data_2 import _ALTERNATIVE_PICTURE_RE, _ALTERNATIVE_TITLE_RE, _ROMAN
from torrcast.domain.compose import _compose
from torrcast.domain.formless import _formless
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

    def one_name(name: str) -> str:
        # Слово формы снимается ТОЛЬКО там, где вид уже сошёлся: в ведре он стоит ключом.
        # Между видами оно не шум, а единственная улика: «Naruto Shippuuden Movie» отличает
        # от сериала «Naruto Shippuuden» ровно слово «Movie», и сняв его, склейка увела бы
        # фильм в пул сериала - подмену, а не двойника.
        return _formless(identity(name))

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
        contested = (picture.kind, identity(picture.title), picture.year) in disputed
        names = set() if contested else {one_name(picture.title)}
        if picture.original:
            names.add(one_name(picture.original))
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
        for name in {(slug := one_name(picture.title)), in_digits(slug)}:
            if name:
                lone.setdefault((picture.kind, name, alternative[i]), []).append(i)
    for i, picture in enumerate(pictures):
        # Псевдоним спрашивается ТОЙ ЖЕ нормализацией, что и ключ ведра: ведро заведено
        # по one_name(), а псевдоним лежит голым слагом, и без выравнивания сторон
        # «Chainsaw Man - The Movie: Reze Arc» перестал бы узнавать своё же ведро.
        for alias in {one_name(a) for a in picture.aliases}:
            for name in (alias, in_digits(alias)):
                if (
                    bucket := lone.get((picture.kind, name, alternative[i]))
                ) is not None and i not in bucket:
                    bucket.append(i)
    for same in lone.values():
        _link(pictures, same, union)

    def subtitle(name: str) -> str:
        head, colon, tail = name.partition(":")
        return identity(tail) if colon and head.strip() else ""

    def one_picture_two_kinds(a: Picture, b: Picture) -> bool:
        # Вид тут и есть весь спор: одно имя, один год, а каталог развёл фильм и сериал.
        # Сойтись им мало имени - «Трансформеры» 2007 года это и фильм, и мультсериал
        # «Transformers: Animated», - поэтому спрашивается оригинал: он либо тот же, либо
        # стоит подзаголовком у соседа («Mater's Tall Tales» в «Cars Toon: Mater's Tall
        # Tales»). Приставка соседом не считается: ею и отличается «Animated».
        if a.kind == b.kind or "other" in (a.kind, b.kind) or not (a.original and b.original):
            return False
        mine, theirs = identity(a.original), identity(b.original)
        return mine == theirs or mine == subtitle(b.original) or theirs == subtitle(a.original)

    kindred: dict[tuple[str, int], list[int]] = {}
    for i, picture in enumerate(pictures):
        if picture.year is not None and picture.original:
            kindred.setdefault((identity(picture.title), picture.year), []).append(i)
    for same in kindred.values():
        for spot, i in enumerate(same):
            for j in same[spot + 1 :]:
                if one_picture_two_kinds(pictures[i], pictures[j]):
                    union(i, j)
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
