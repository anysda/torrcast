"""Зеркало :mod:`torrcast.domain._config_hls`: чем и куда раздаётся лента."""

from __future__ import annotations

from dataclasses import fields

from torrcast.domain._config_hls import _ConfigHls
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS


def test_the_hls_keys_ride_in_config_with_the_cautious_defaults() -> None:
    """Раздача приезжает в конфиг целиком, а её умолчания - от осторожного профиля."""
    hls = {field.name for field in fields(_ConfigHls)}
    config = Config()

    assert hls <= {field.name for field in fields(Config)}
    assert (config.hls_burst, config.hls_segment) == (
        CAUTIOUS.burst,
        CAUTIOUS.segment_seconds,
    )


def test_the_seek_thresholds_arrive_as_keys_with_cautious_defaults() -> None:
    """Порог ожидания и задел стыка стали настройкой: без ключа их не перебить профилем."""
    config = Config()

    assert (config.hls_jump, config.hls_seam_lead) == (CAUTIOUS.jump, CAUTIOUS.seam_lead)
    assert (config.hls_jump, config.hls_seam_lead) == (15.0, 60.0)
