"""Зеркало :mod:`torrcast.domain._config_sources`: с кем показ разговаривает по сети."""

from __future__ import annotations

from dataclasses import fields

from torrcast.domain._config_sources import _ConfigSources
from torrcast.domain.config import Config


def test_the_network_keys_come_first_and_tv_stays_the_only_required_one() -> None:
    """Ключи хозяйства открывают конфиг: порядок полей - часть договора его сборки."""
    names = [field.name for field in fields(Config)]
    mine = [field.name for field in fields(_ConfigSources)]

    assert names[: len(mine)] == mine
    assert Config().tv is None
