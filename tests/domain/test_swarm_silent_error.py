"""Зеркало :mod:`torrcast.domain.swarm_silent_error`: место молчания роя в иерархии ошибок.

Мера про одно решение: молчание роя обязано ловиться там же, где ловятся все беды
инфраструктуры, и при этом отличаться от приговора файлу - иначе полка запомнила бы
холодную раздачу как негодный файл.
"""

import pytest

from torrcast.domain.infra_error import InfraError
from torrcast.domain.swarm_silent_error import SwarmSilentError
from torrcast.domain.torrcast_error import TorrcastError


def test_the_silent_swarm_is_still_an_infra_trouble() -> None:
    """Прежние ловцы не должны замечать разницы: `except InfraError` берёт и его."""
    assert issubclass(SwarmSilentError, InfraError)
    assert issubclass(SwarmSilentError, TorrcastError)
    with pytest.raises(InfraError):
        raise SwarmSilentError("рой молчит")


def test_a_verdict_about_the_file_is_not_a_silent_swarm() -> None:
    """Обратное неверно, и на этом стоит запоминание: `InfraError` про файл ловится
    отдельно от молчания роя, иначе его тоже запомнили бы на сутки."""
    with pytest.raises(InfraError):
        try:
            raise InfraError("индекс Cues врёт")
        except SwarmSilentError:  # pragma: no cover - ветка обязана быть недостижимой
            raise AssertionError("приговор файлу опознан как молчание роя") from None
