"""Правило slugify; используют модели и фасады разбора имён."""

from __future__ import annotations

import re
import unicodedata

from torrcast.domain._name_data.data_3 import _NUMERO_RE


def slugify(text: str) -> str:
    plain = _NUMERO_RE.sub(" ", text)
    normalized = unicodedata.normalize("NFKC", plain).casefold().replace("ё", "е")
    return re.sub("[^0-9a-zа-я]+", "-", normalized).strip("-")


__all__ = ["slugify"]
