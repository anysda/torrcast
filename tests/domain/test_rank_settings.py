"""Проверяет пороги ранжирования."""

from torrcast.domain.rank_settings import ALIVE_SEEDERS, DISC_RE


def test_rank_settings_keep_product_thresholds() -> None:
    assert ALIVE_SEEDERS == 5
    assert DISC_RE.search("BDMV")
