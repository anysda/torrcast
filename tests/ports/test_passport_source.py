"""Проверяет, что боевая справка и её подделка подходят порту паспорта."""

from tests.fakes.passport import FakePassport
from torrcast.domain.facts.origin import Origin
from torrcast.facts import origin
from torrcast.ports.passport_source import PassportSource


def test_live_origin_fits_the_port() -> None:
    """Договор порта выполняет сама :func:`torrcast.facts.origin` - переходника нет."""
    port: PassportSource = origin
    assert callable(port)


def test_fake_passport_answers_by_the_port() -> None:
    """Подделка справки отвечает тем же вызовом, что и боевая: имя, тип, потолок."""
    port: PassportSource = FakePassport({"кино": Origin(title="Movie", year=2019)})
    assert port("кино", series=False, budget=0.1) == Origin(title="Movie", year=2019)
    assert port("чего нет") == Origin()
