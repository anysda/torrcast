"""Правило parse voices; используют модели и фасады разбора имён."""

from __future__ import annotations

import re

from torrcast.domain._name_data.data_1 import _TAG_ONLY_RE, _TAG_VOICES, _VOICES


def _parse_voices(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for pattern, label in _VOICES:
        if re.search(pattern, text, re.IGNORECASE) and label not in found:
            found.append(label)
    for segment in re.split("[|/]", text)[1:]:
        if not _TAG_ONLY_RE.match(segment):
            continue
        for code in re.findall("[DPAL]2?", segment):
            label = _TAG_VOICES.get(code) or _TAG_VOICES[code[0]]
            if label not in found:
                found.append(label)
    order = {label: i for i, (_, label) in enumerate(_VOICES)}
    return tuple(sorted(found, key=lambda v: order.get(v, 99)))


__all__ = ["_parse_voices"]
