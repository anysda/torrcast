"""Зеркало :mod:`torrcast.domain._config_recode`: пороги веса и перекодирование."""

from __future__ import annotations

from dataclasses import fields

from torrcast.domain._config_recode import _ConfigRecode
from torrcast.domain.config import Config


def test_the_weight_keys_ride_in_config_and_keep_their_ladder() -> None:
    """Пороги веса приезжают в конфиг целиком и остаются лестницей, а не россыпью."""
    weight = {field.name for field in fields(_ConfigRecode)}
    config = Config()

    assert weight <= {field.name for field in fields(Config)}
    assert config.recode_mbit < config.recode_at_mbit <= config.bitrate_warn_mbit
