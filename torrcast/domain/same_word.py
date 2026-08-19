"""Правило same word; используют модели и фасады разбора имён."""

from __future__ import annotations

import os.path

from torrcast.domain._name_data.data_1 import _CYRILLIC
from torrcast.domain._name_data.data_3 import _ENDING, _STEM
from torrcast.domain.spell import spell


def same_word(one: str, two: str) -> bool:
    if one == two:
        return True
    if bool(_CYRILLIC.search(one)) != bool(_CYRILLIC.search(two)):
        one, two = (spell(one), spell(two))
        if one == two:
            return True
    common = len(os.path.commonprefix([one, two]))
    return common >= _STEM and len(one) - common <= _ENDING and (len(two) - common <= _ENDING)


__all__ = ["same_word"]
