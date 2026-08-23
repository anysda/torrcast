"""Потолок приёмника в отборе: раздача, которую играют без перекода и без каши."""

from __future__ import annotations

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.usecases.rank.fits_receiver import fits_receiver


def test_a_release_under_the_receiver_ceiling_fits() -> None:
    """~8 ГБ на два часа это 9.5 Мбит/с, ~16 ГБ - 19.1: первую приёмник играет как есть."""
    assert fits_receiver(rel(size_gb=8), RUNTIME, 10.0, 0.0)
    assert not fits_receiver(rel(size_gb=16), RUNTIME, 10.0, 0.0)


def test_the_ceiling_is_the_receivers_own_number() -> None:
    """У приставки он 28.0, и та же раздача ложится под него без всякого перекода."""
    assert not fits_receiver(rel(size_gb=16), RUNTIME, 10.0, 0.0)
    assert fits_receiver(rel(size_gb=16), RUNTIME, 28.0, 0.0)


def test_without_recoding_the_step_is_flat() -> None:
    """Ноль - перекодирования нет, играть тяжёлое всё равно нечем, предпочитать нечего."""
    assert not fits_receiver(rel(size_gb=8), RUNTIME, 0.0, 0.0)


def test_a_dead_swarm_is_no_win_at_any_bitrate() -> None:
    """Менять перекод на подгрузы незачем: один-два сида - это не рой."""
    assert not fits_receiver(rel(size_gb=8, seeders=2), RUNTIME, 10.0, 0.0)
    assert fits_receiver(rel(size_gb=8, seeders=5), RUNTIME, 10.0, 0.0)


def test_an_unknown_weight_never_claims_to_fit() -> None:
    """🔴 TC-344. Предпочитать по весу, которого нет, нельзя."""
    silent = rel(name="Локи [S01]", kind="tv", size_gb=1)
    assert not fits_receiver(silent, RUNTIME, 10.0, 0.0)


#: 12 Мбит/с на два часа: тяжёлый сосед из пробы, ради которой пол и заведён.
HEAVY = 12.0


def test_a_named_frame_at_a_junk_bitrate_does_not_win_the_step() -> None:
    """Раздача, названная 1080p, при 0.05 Мбит/с - каша, и ступень её не поднимает.

    Ровно то, чего у ступени не было: условие «легче потолка» бездонно, и мусор проходил
    его вольготнее честной раздачи. Признак старья тут молчит - имя назвало кадр.
    """
    junk = rel(size_gb=0.042, seeders=60)
    assert not fits_receiver(junk, RUNTIME, 10.0, HEAVY)
    assert fits_receiver(junk, RUNTIME, 10.0, 0.0)


def test_the_floor_is_measured_by_the_neighbour_the_step_displaces() -> None:
    """Пол считается от тяжёлого соседа: 1.5 Мбит/с против 12 - каша, против 9 - размен."""
    thin = rel(size_gb=1.26, seeders=60)
    assert not fits_receiver(thin, RUNTIME, 10.0, HEAVY)
    assert fits_receiver(thin, RUNTIME, 10.0, 9.0)


def test_a_deep_but_lawful_trade_keeps_the_step() -> None:
    """Аниме на 3.54 Мбит/с вместо 16.22 - самый глубокий законный размен корпуса.

    Абсолютным числом его от каши не отделить: игровое кино на этом битрейте уже каша, а
    рисованная картинка - нет. Доля отделяет, потому что обе стороны - одна картина.
    """
    lean = rel(size_gb=2.967, seeders=6)
    assert fits_receiver(lean, RUNTIME, 10.0, 16.22)


def test_without_a_heavy_neighbour_the_floor_says_nothing() -> None:
    """Менять не на что - размена нет, и пол в споре не участвует."""
    assert fits_receiver(rel(size_gb=0.042, seeders=60), RUNTIME, 10.0, 0.0)
