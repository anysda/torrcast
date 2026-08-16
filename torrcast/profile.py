"""Совместимый фасад профиля приёмника и обвязка внешнего состояния."""

from typing import TYPE_CHECKING, Final

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

_SEEN: dict[str, Choice] = {}
PASSPORT_TIMEOUT: Final = 2.0


def detect(config: "Config") -> Choice:
    """Выбрать профиль: ручной ключ, затем сохранённый или опрошенный паспорт."""
    named = str(getattr(config, "receiver_profile", "") or "")
    if named:
        chosen = by_key(named)
        if chosen is not None:
            return Choice(chosen, f"назван руками: receiver_profile={chosen.key}")
        return Choice(CAUTIOUS, f"профиля «{named}» нет - беру осторожный")
    address = str(config.tv or "")
    if config.receiver != "chromecast" or not address:
        return Choice(CAUTIOUS, "приёмника с паспортом нет - беру осторожный")
    if address not in _SEEN:
        _SEEN[address] = _asked(address)
    return _SEEN[address]


def _asked(address: str) -> Choice:
    from torrcast.scan import named as ask

    try:
        device = ask(address, timeout=PASSPORT_TIMEOUT)
    except Exception:
        return Choice(CAUTIOUS, "приёмник не ответил - беру осторожный")
    passport = ", ".join(part for part in (device.maker, device.model, device.name) if part)
    if not passport:
        return Choice(CAUTIOUS, "приёмник не представился - беру осторожный")
    return Choice(for_passport(device.maker, device.model, device.name), f"по паспорту: {passport}")


def forget() -> None:
    """Очистить кэш паспортов приёмников."""
    _SEEN.clear()


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
