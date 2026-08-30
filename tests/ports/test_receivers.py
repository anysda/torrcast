"""Проверяет контракт завода приёмника и поведение его фейка."""

from tests.fakes.receivers import FakeReceivers
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.ports.receivers import Receivers


def test_the_address_and_the_kind_reach_the_factory() -> None:
    factory = FakeReceivers()
    port: Receivers = factory
    port("chromecast", "192.0.2.10")
    assert factory.asked == [("chromecast", "192.0.2.10", "", CAUTIOUS)]


def test_a_show_over_tls_carries_its_trust_anchor() -> None:
    """Пустой корень - показ едет без TLS; названный обязан доехать до приёмника."""
    factory = FakeReceivers()
    port: Receivers = factory
    port("chromecast", "192.0.2.10", "/etc/torrcast/ca.pem")
    assert factory.asked[-1][2] == "/etc/torrcast/ca.pem"


def test_the_device_profile_travels_with_the_receiver() -> None:
    """Профиль устройства - часть заказа: по нему приёмник решает, что он потянет."""
    factory = FakeReceivers()
    port: Receivers = factory
    strict = Profile(key="strict", title_key="receiver.profile_cautious")
    port("chromecast", "192.0.2.10", profile=strict)
    assert factory.asked[-1][3] is strict


def test_one_receiver_serves_the_whole_unit() -> None:
    """Приёмник один на юнит, а не на серию: иначе на стыке серий их оказывается два."""
    factory = FakeReceivers()
    port: Receivers = factory
    assert port("chromecast", "192.0.2.10") is port("chromecast", "192.0.2.10")
