"""Проверяет срок жизни добора справки: русский прежний, чужой с доплатой за волну."""

import pytest

from torrcast.domain.catalogs.tongue import EN, RU, _choose_tongue
from torrcast.domain.facts.facts_budget import facts_budget
from torrcast.domain.facts.settings import HTTP_TIMEOUT, TOPUP_LIMIT
from torrcast.domain.facts.topup_limit import topup_limit


def test_the_russian_topup_lives_exactly_as_long_as_it_lived_before() -> None:
    """🔴 Русский показ не платит за правку ни сотой: у него как была одна волна, так и есть."""
    _choose_tongue(RU)

    assert topup_limit() == TOPUP_LIMIT


def test_a_foreign_tongue_keeps_its_topup_alive_through_the_extra_wave() -> None:
    """🔴 TC-957. Не дорасти сроку - поток добора умирал бы на третьем шаге под чужим языком.

    Кэш тогда оставался бы пустым навсегда, и КАЖДОЕ английское меню шло бы в сеть за тем
    же самым заново и снова печаталось голым.
    """
    _choose_tongue(EN)

    assert topup_limit() == pytest.approx(TOPUP_LIMIT + HTTP_TIMEOUT)


def test_the_topup_outlives_the_menu_on_every_tongue() -> None:
    """Кэш дописывается уже после меню - иначе следующий показ снова идёт в сеть."""
    for language in (RU, EN):
        _choose_tongue(language)
        assert facts_budget() < topup_limit()
