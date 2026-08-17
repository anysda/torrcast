"""Выбор приёмника по имени: живой Chromecast или сухой приёмник автономной приёмки."""

from __future__ import annotations

import pytest

from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver
from torrcast.adapters.chromecast.cast.make_receiver import make_receiver
from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS, Profile


def test_the_live_receiver_is_built_by_name_and_keeps_its_profile() -> None:
    """Корень запуска знает только имя, а профиль едет в приёмник вместе с ним."""
    profile = Profile(key="stick", title="приставка")

    made = make_receiver("chromecast", address="10.0.0.50", profile=profile)

    assert isinstance(made, ChromecastReceiver)
    assert made.address == "10.0.0.50"
    assert made.profile is profile


def test_the_dry_receiver_is_built_by_the_same_name_and_needs_no_address() -> None:
    """Автономная приёмка идёт без телевизора вовсе: адреса у неё нет и быть не может."""
    made = make_receiver("mock")

    assert isinstance(made, MockReceiver)


def test_the_live_receiver_without_an_address_refuses_with_a_way_out() -> None:
    """Пустой адрес - не приёмник, и человеку сразу сказано, чем найти телевизор."""
    with pytest.raises(InfraError, match="cast --tv"):
        make_receiver("chromecast")


def test_the_default_profile_is_the_cautious_one() -> None:
    """Показ без выбранного профиля ведёт себя как раньше."""
    made = make_receiver("chromecast", address="10.0.0.50")

    assert isinstance(made, ChromecastReceiver)
    assert made.profile is CAUTIOUS
