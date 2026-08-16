"""Правило pick franchise; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.aliases import _aliases
from torrcast.domain.both_languages import _both_languages
from torrcast.domain.by_alias import _by_alias
from torrcast.domain.by_both_names import _by_both_names
from torrcast.domain.by_subtitle import _by_subtitle
from torrcast.domain.by_words import _by_words
from torrcast.domain.confirmed_continuations import confirmed_continuations
from torrcast.domain.franchise_item_key import _franchise_item_key
from torrcast.domain.franchises import franchises
from torrcast.domain.group_weight import _group_weight
from torrcast.domain.in_digits import in_digits
from torrcast.domain.numbered import _numbered
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify
from torrcast.domain.spell import spell
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.domain.with_subtitled import _with_subtitled


def pick_franchise(
    query: str, pictures: list[Picture], *, join_continuations: bool = True
) -> list[Picture]:
    groups = franchises(pictures)
    aliases = _aliases(groups)
    digits = {in_digits(key): key for key in groups}
    spelled: dict[str, str] = {}
    for written, target in sorted(aliases.items()):
        spelled.setdefault(spell(written), target)
    third: dict[str, str] = {}
    for group_key, items in groups.items():
        for picture in items:
            for slug in picture.aliases:
                if not slug or slug in groups or slug in aliases:
                    continue
                if third.setdefault(slug, group_key) != group_key:
                    third[slug] = ""

    def named(name: str) -> str | None:
        wanted = slugify(name)
        if not wanted:
            return None
        pointed = aliases.get(wanted)
        if wanted in groups:
            if (
                pointed is not None
                and pointed != wanted
                and (_group_weight(groups, pointed) > _group_weight(groups, wanted))
            ):
                return pointed
            return wanted
        if pointed is not None:
            return pointed
        if (counted := in_digits(wanted)) in digits:
            return digits[counted]
        return None

    def lookup(name: str) -> str | None:
        if (exact := named(name)) is not None:
            return exact
        wanted = slugify(name)
        if not wanted:
            return None
        if pointed := third.get(wanted):
            return pointed
        if hits := [k for k in groups if wanted in k]:
            return min(hits, key=lambda key: (len(key), -_group_weight(groups, key), key))
        if loose := _by_words(wanted, groups):
            return loose
        if hits := [k for k in groups if k and k in wanted]:
            return max(hits, key=len)
        return spelled.get(spell(wanted))

    name, index = split_franchise_index(query)
    key = lookup(name)
    if key is None:
        key, index = (lookup(query), None)
    if key is None:
        items = _by_subtitle(name, pictures) or _by_alias(name, pictures)
        if not items:
            items = _by_subtitle(query, pictures) or _by_alias(query, pictures)
            index = None
        if not items:
            items, index = (_by_both_names(query, pictures), None)
        return _numbered(items, index)
    franchise_items = _both_languages(groups, aliases, key)
    if index is None and join_continuations:
        seen = {p.key for p in franchise_items}
        franchise_items = sorted(
            franchise_items
            + [
                p
                for p in confirmed_continuations(groups, key, franchise_items)
                if p.key not in seen
            ],
            key=_franchise_item_key,
        )
        continuation_groups = {
            grouped_key: [p for p in grouped_items if p.kind != "other"]
            for grouped_key, grouped_items in groups.items()
            if grouped_key.startswith(f"{key}-и-")
        }
        continuation_groups = {k: items for k, items in continuation_groups.items() if items}
        if len(continuation_groups) >= 2:
            continuations = [p for items in continuation_groups.values() for p in items]
            known = {p.key for p in continuations}
            franchise_items = sorted(
                [p for p in franchise_items if p.kind != "other" and p.key not in known]
                + continuations,
                key=_franchise_item_key,
            )
    items = _numbered(franchise_items, index)
    if not items and index is not None and ((whole_name := named(query)) is not None):
        items = _both_languages(groups, aliases, whole_name)
    return _with_subtitled(items, name, pictures, index)


__all__ = ["pick_franchise"]
