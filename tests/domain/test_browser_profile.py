"""Проверяет измеренный профиль приёмника-вкладки."""

from torrcast.domain.browser_profile import BROWSER
from torrcast.domain.segment_container import FMP4


def test_browser_profile_keeps_its_public_identity() -> None:
    """Разрез модуля не превращает именованный профиль в безымянный набор чисел."""
    assert BROWSER.key == "browser"
    assert "browser" in BROWSER.title
    assert BROWSER.segment_container == FMP4


def test_browser_profile_recode_ceiling_is_the_measured_value() -> None:
    """Потолок перекода - снятое число (50.0), а не гипотеза ТЗ (20.0)."""
    assert BROWSER.recode_at_mbit == 50.0
    assert BROWSER.recode_mbit == 50.0
    assert BROWSER.warn_mbit == 50.0


def test_browser_profile_staleness_matches_the_card() -> None:
    """Обе границы молчания - слово карточки: lost на 15 с, закрытие на 60 с."""
    assert BROWSER.lost_after == 15.0
    assert BROWSER.gone_after == 60.0
