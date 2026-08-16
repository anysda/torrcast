"""Правило normalize; используют модели и фасады разбора имён."""

from __future__ import annotations

import re
import unicodedata

from torrcast.domain._name_data import _NUMERO_RE


def _normalize(name: str) -> str:
    text = unicodedata.normalize("NFKC", _NUMERO_RE.sub(" ", name)).replace("\xa0", " ")
    text = text.replace("–", "-").replace("—", "-").replace("‐", "-")
    text = re.sub("(\\d{3,4})\\s*р\\b", "\\1p", text)
    return re.sub("\\s+", " ", text).strip()


__all__ = ["_normalize"]
