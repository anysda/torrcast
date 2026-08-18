"""Зеркало договора о профиле тяжести: настоящий счётчик отвечает ему целиком."""

from __future__ import annotations

from tests.usecases.playback.world import film_keys, grid
from torrcast.recode import Weights
from torrcast.usecases.playback.heavy_profile import HeavyProfile


def test_the_real_profile_answers_the_named_contract() -> None:
    """Показ спрашивает у профиля одно число - средний битрейт по карте, - и получает его."""
    made = Weights.of(film_keys(), grid())

    assert made is not None
    named: HeavyProfile = made

    assert named.container > 0.0


def test_a_map_without_offsets_is_no_profile_at_all() -> None:
    """Карта прошлой версии смещений не несёт - профиля по ней не построить."""
    keys = film_keys()

    assert Weights.of(keys._replace(offset=[]), grid()) is None
