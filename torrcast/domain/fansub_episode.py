"""Правило fansub episode; используют модели и фасады разбора имён."""

from __future__ import annotations

import re

from torrcast.domain._name_data import _FANSUB_EPISODE_RE
from torrcast.domain.find_year import _find_year


def _fansub_episode(text: str) -> re.Match[str] | None:
    if _find_year(text)[0] is not None:
        return None
    return _FANSUB_EPISODE_RE.match(text)


__all__ = ["_fansub_episode"]
