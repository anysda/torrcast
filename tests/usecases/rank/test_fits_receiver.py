"""Потолок приёмника в отборе: раздача, которую играют без перекода на ходу."""

from __future__ import annotations

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.usecases.rank.fits_receiver import fits_receiver


def test_a_release_under_the_receiver_ceiling_fits() -> None:
    """~8 ГБ на два часа это 9.5 Мбит/с, ~16 ГБ - 19.1: первую приёмник играет как есть."""
    assert fits_receiver(rel(size_gb=8), RUNTIME, 10.0)
    assert not fits_receiver(rel(size_gb=16), RUNTIME, 10.0)


def test_the_ceiling_is_the_receivers_own_number() -> None:
    """У приставки он 28.0, и та же раздача ложится под него без всякого перекода."""
    assert not fits_receiver(rel(size_gb=16), RUNTIME, 10.0)
    assert fits_receiver(rel(size_gb=16), RUNTIME, 28.0)


def test_without_recoding_the_step_is_flat() -> None:
    """Ноль - перекодирования нет, играть тяжёлое всё равно нечем, предпочитать нечего."""
    assert not fits_receiver(rel(size_gb=8), RUNTIME, 0.0)


def test_a_dead_swarm_is_no_win_at_any_bitrate() -> None:
    """Менять перекод на подгрузы незачем: один-два сида - это не рой."""
    assert not fits_receiver(rel(size_gb=8, seeders=2), RUNTIME, 10.0)
    assert fits_receiver(rel(size_gb=8, seeders=5), RUNTIME, 10.0)


def test_an_unknown_weight_never_claims_to_fit() -> None:
    """🔴 TC-344. Предпочитать по весу, которого нет, нельзя."""
    silent = rel(name="Локи [S01]", kind="tv", size_gb=1)
    assert not fits_receiver(silent, RUNTIME, 10.0)
