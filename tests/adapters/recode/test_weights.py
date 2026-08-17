"""Профиль тяжести: Мбит/с каждого сегмента по карте, поправка на лишние дорожки и вес копии."""

from __future__ import annotations

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode.weights import PASSPORT_WEIGHT, Weights


def test_the_profile_is_known_before_a_single_segment_is_packed() -> None:
    """Байты и секунды каждого сегмента считаются из карты опорных кадров - даром."""
    lines = grid()
    weights = Weights.of(keys(rate=2.0e6), lines)

    assert weights is not None
    assert len(weights.raw) == lines.count
    assert weights.at(0) == 16.0, "2 МБ/с - это ровно 16 Мбит/с"
    assert weights.container == 16.0


def test_a_map_without_offsets_gives_no_profile_at_all() -> None:
    """Кэш прежней версии смещений не несёт, и врать по нему нельзя."""
    old = keys()
    blind = old.__class__(duration=300.0, at=old.at, offset=[], kind="mkv")

    assert Weights.of(blind, grid()) is None


def test_the_passport_sets_the_correction_at_once_and_with_weight() -> None:
    """Дан средний битрейт по паспорту - поправка «контейнер → ТВ» известна сразу и точно."""
    weights = Weights.of(keys(rate=2.0e6), grid(), delivered=12.0)

    assert weights is not None
    assert weights.extra == 4.0, "контейнер 16 Мбит/с, на ТВ уезжает 12"
    assert weights.measured == PASSPORT_WEIGHT
    assert weights.at(0) == 12.0


def test_the_correction_is_learnt_from_a_real_published_copy() -> None:
    """Скользящее среднее: одиночный сегмент может соврать, десяток - уже нет."""
    weights = Weights.of(keys(rate=2.0e6), grid())
    assert weights is not None

    weights.calibrate(slot=0, size=int(12.0e6 * 10.0 / 8), span=10.0)

    assert weights.measured == 1
    assert weights.extra == 4.0
    assert weights.at(0) == 12.0


def test_a_recoded_or_truncated_segment_is_not_learnt_from() -> None:
    """Лишние дорожки не могут весить больше половины контейнера - это уже не поправка."""
    weights = Weights.of(keys(rate=2.0e6), grid())
    assert weights is not None

    weights.calibrate(slot=0, size=1000, span=10.0)  # перекодированный кусок
    weights.calibrate(slot=0, size=int(20.0e6 * 10.0 / 8), span=10.0)  # тяжелее карты

    assert weights.measured == 0 and weights.extra == 0.0


def test_heavy_and_bulky_are_two_different_measures() -> None:
    """Битрейт и вес куска не совпадают: длинный кусок бывает увесистым и на скромных Мбит/с."""
    lines = grid()
    weights = Weights.of(keys(rate=2.0e6), lines)
    assert weights is not None

    assert weights.heavy(15.0) == tuple(range(lines.count)), "16 Мбит/с выше порога 15"
    assert weights.heavy(20.0) == (), "порог выше профиля - тяжёлых нет"
    assert weights.bulky(lines, cap=100_000_000) == (), "потолок веса выше любого куска"
    assert weights.size(0, 10.0) == 16.0 * 10.0 * 1e6 / 8, "честный вес копии по карте"


def test_a_slot_outside_the_map_answers_zero_instead_of_raising() -> None:
    """Профиль спрашивают из горячего пути, и падать он там права не имеет."""
    weights = Weights.of(keys(rate=2.0e6), grid())
    assert weights is not None

    assert weights.at(-1) == 0.0 and weights.at(10_000) == 0.0
