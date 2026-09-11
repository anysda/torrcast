"""Русские надписи кластера выбора профиля приёмника."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера выбора профиля приёмника."""
    return {
        "profile_detector.named_manually": "назван руками: receiver_profile={profile_key}",
        "profile_detector.unknown_named_profile": "профиля «{name}» нет - беру осторожный",
        "profile_detector.no_passport_receiver": "приёмника с паспортом нет - беру осторожный",
        "profile_detector.no_response": "приёмник не ответил - беру осторожный",
        "profile_detector.no_introduction": "приёмник не представился - беру осторожный",
        "profile_detector.by_passport_prefix": "по паспорту:",
    }
