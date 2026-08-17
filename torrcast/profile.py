"""Совместимый фасад профиля приёмника и обвязка внешнего состояния."""

from typing import TYPE_CHECKING

from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.domain.by_key import by_key
from torrcast.domain.choice import Choice
from torrcast.domain.for_passport import for_passport
from torrcast.domain.profile import (
    ANDROID_TV,
    CAUTIOUS,
    COPY,
    PROFILES,
    RECODE,
    REFUSE,
    Profile,
    Verdict,
)
from torrcast.domain.thresholds import thresholds
from torrcast.domain.tune import tune

if TYPE_CHECKING:
    from torrcast.state import Config

__all__ = [
    "ANDROID_TV",
    "CAUTIOUS",
    "COPY",
    "PROFILES",
    "RECODE",
    "REFUSE",
    "Choice",
    "Profile",
    "Verdict",
    "by_key",
    "detect",
    "for_passport",
    "forget",
    "thresholds",
    "trace_thresholds",
    "tune",
]


def detect(config: "Config") -> Choice:
    """Выбрать профиль: ручной ключ, затем сохранённый или опрошенный паспорт.

    Сам выбор - опрос живого устройства, то есть адаптер. Фасад только зовёт ОДИН его
    экземпляр: кэш паспортов у прежних имён и у проб ``cast doctor`` обязан быть общим.
    """
    return detector.detect(config)


def forget() -> None:
    """Очистить кэш паспортов приёмников."""
    detector.forget()


def trace_thresholds(config: "Config", profile: Profile) -> dict[str, object]:
    """Прочитать сохранённые настройки и собрать снимок порогов начала серии."""
    from torrcast import TorrcastError
    from torrcast.state import config_keys, load_config

    try:
        raw = load_config()
    except TorrcastError:
        return {"profile_source": "конфиг не прочитан"}
    chosen = detect(raw)
    values, sources = thresholds(raw, config, profile, config_keys())
    return {
        "profile_source": (
            "паспорт приёмника" if chosen.how.startswith("по паспорту:") else chosen.how
        ),
        "thresholds": values,
        "threshold_sources": sources,
    }
