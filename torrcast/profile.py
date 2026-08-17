"""Совместимый фасад профиля приёмника и обвязка внешнего состояния.

Правила выбора живут в :mod:`torrcast.domain.profile`, опрос устройства и память о нём -
в :class:`~torrcast.adapters.chromecast.profile_detector.ProfileDetector`, снимок порогов
для ленты - в :mod:`torrcast.runtime.trace_thresholds`. Наружу отдаются методы ОДНОГО
экземпляра детектора: кэш паспортов у прежних имён и у проб ``cast doctor`` общий.
"""

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
from torrcast.runtime.trace_thresholds import trace_thresholds

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

#: Выбрать профиль: ручной ключ, затем сохранённый или опрошенный паспорт.
detect = detector.detect
#: Очистить кэш паспортов приёмников.
forget = detector.forget
