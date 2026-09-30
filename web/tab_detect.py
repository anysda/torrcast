"""Профиль, которым процесс страницы судит поиск, карточку и прогрев.

Их зовёт процесс страницы по своим поводам, и довода вкладки им не протянуть: им
достаётся последний услышанный ключ (:func:`web.hear.hear`). Разойдись он с ключом
показа - промахнётся только прогрев, пороги показа решает его собственный ключ.
"""

from __future__ import annotations

from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.for_tab import for_tab
from web.hear import _HEARD

__all__ = ["tab_detect"]


def tab_detect(config: Config) -> Choice:
    """Профиль поиска и прогрева: тот же, что получит показ последней услышанной вкладки."""
    return for_tab(detector.detect(config), config, _HEARD["tab"])
