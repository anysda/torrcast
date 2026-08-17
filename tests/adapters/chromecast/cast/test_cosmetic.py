"""Фильтр косметической строки: гасит ровно одну жалобу и ничего кроме неё."""

from __future__ import annotations

import logging

from torrcast.adapters.chromecast.cast.cosmetic import _DIAL_LOGGER, _Cosmetic


def _record(message: str) -> logging.LogRecord:
    made = logging.LogRecord(_DIAL_LOGGER, logging.WARNING, __file__, 1, None, None, None)
    made.msg = message
    return made


def test_the_one_cosmetic_line_is_dropped() -> None:
    """Жалоба на 8443 печаталась на КАЖДОМ подключении и стоила ложной гипотезы.

    ``port=8009`` внутри её текста сбивал с толку отдельно: это распечатка списка
    сервисов устройства, а не отказавший порт.
    """
    noise = _record(
        "Failed to determine cast type for host 10.0.0.50 (Connection refused) (services:...)"
    )

    assert _Cosmetic().filter(noise) is False


def test_real_complaints_still_reach_the_human() -> None:
    """Глушится ОДНО сообщение, а не логгер: настоящие жалобы обязаны доходить."""
    real = _record("Failed to connect to service HostServiceInfo(host='10.0.0.50', port=8009)")

    assert _Cosmetic().filter(real) is True


def test_the_pattern_is_matched_before_the_address_is_substituted() -> None:
    """Фильтр стоит на логгере и видит ШАБЛОН, а не готовый текст.

    Сравнивай он готовую строку - жалоба проходила бы мимо на любом адресе, кроме
    того, на котором фильтр писали.
    """
    template = _record("Failed to determine cast type for host %s (%s)")

    assert _Cosmetic().filter(template) is False
    assert _Cosmetic.NOISE == "Failed to determine cast type"


def test_the_filter_hangs_on_the_library_logger_and_not_on_ours() -> None:
    """Чужая библиотека не трогается: фильтр вешается снаружи, на её логгер."""
    assert _DIAL_LOGGER == "pychromecast.dial"
