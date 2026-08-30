"""Свежий язык продукта из настройки, с безопасным английским умолчанием."""

from __future__ import annotations

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.catalogs.tongue import EN
from torrcast.domain.torrcast_error import TorrcastError


def chosen_language() -> str:
    """Прочитать язык сейчас; битая настройка не превращает оформление в отказ."""
    try:
        return load_config().language
    except TorrcastError:
        return EN
