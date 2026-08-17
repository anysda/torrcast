"""Раздача - приложение к картине: так сказало имя, так вышло по весу."""

from __future__ import annotations

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.usecases.rank.is_extra import is_extra


def test_a_light_making_of_is_thrown_out() -> None:
    """🔴 TC-290. «Тачки 2»: HDRip «фильм о фильме» на 0.4 ГБ стоял дефолтом Enter."""
    made = rel(name="Тачки 2: фильм о фильме (2011) HDRip", title="Тачки 2", size_gb=0.4)
    assert is_extra(made, RUNTIME)


def test_a_sure_marker_is_judged_without_any_weight() -> None:
    """🔴 TC-339. «Дополнительные материалы» не бывают картиной ни при каком битрейте."""
    disc = rel(name="Титаник | Дополнительные материалы", title="Титаник", size_gb=11.6)
    assert is_extra(disc, RUNTIME)


def test_an_ambiguous_marker_on_a_heavy_release_stays() -> None:
    """Столько ролик не весит, а ошибиться тут дорого: порядок утопит его и без ворот."""
    heavy = rel(name="Тачки 2: фильм о фильме (2011) BDRip", title="Тачки 2", size_gb=11.6)
    assert not is_extra(heavy, RUNTIME)


def test_a_picture_without_the_marker_is_never_an_extra() -> None:
    assert not is_extra(rel(size_gb=0.4), RUNTIME)


def test_an_unknown_weight_does_not_throw_the_release_out() -> None:
    """🔴 TC-344. Выкидывать по весу, которого нет, значит карать за своё незнание."""
    pack = rel(name="Локи: за кадром [S01]", title="Локи", kind="tv", size_gb=0.4)
    assert not is_extra(pack, RUNTIME)
