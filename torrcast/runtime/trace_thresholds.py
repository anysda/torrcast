"""Снимок порогов начала серии: чем играем и откуда взято каждое число."""

from __future__ import annotations

from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.adapters.filesystem.state import config_keys, load_config
from torrcast.domain.config import Config
from torrcast.domain.profile import Profile
from torrcast.domain.thresholds import thresholds
from torrcast.domain.torrcast_error import TorrcastError


def trace_thresholds(config: Config, profile: Profile) -> dict[str, object]:
    """Прочитать сохранённые настройки и собрать снимок порогов начала серии.

    Снимок берётся на каждой серии, поэтому непрочитанный конфиг - это строка в ленте,
    а не конец показа.
    """
    try:
        raw = load_config()
    except TorrcastError:
        return {"profile_source": "конфиг не прочитан"}
    chosen = detector.detect(raw)
    values, sources = thresholds(raw, config, profile, config_keys())
    return {
        "profile_source": (
            "паспорт приёмника" if chosen.how.startswith("по паспорту:") else chosen.how
        ),
        "thresholds": values,
        "threshold_sources": sources,
    }
