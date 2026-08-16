"""Правило aliases; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.franchise_key import franchise_key
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify


def _aliases(groups: dict[str, list[Picture]]) -> dict[str, str]:
    weight = {key: sum(len(p.releases) for p in items) for key, items in groups.items()}
    aliases: dict[str, str] = {}
    for key, items in groups.items():
        for picture in items:
            if not picture.original:
                continue
            for name in (franchise_key(picture.original), slugify(picture.original)):
                if name and weight[key] > weight.get(aliases.get(name, ""), 0):
                    aliases[name] = key
    return aliases


__all__ = ["_aliases"]
