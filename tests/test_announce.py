"""Зеркало объявления: два стенда в одной сети не спорят за одно имя службы."""

from __future__ import annotations

from hass.announce import ANCHOR, SERVICE, Announce


def test_the_service_name_carries_the_host_so_two_stands_do_not_collide() -> None:
    one = Announce(8479, version="1.0.3", tv="10.0.1.7", host="tv-samsung")
    two = Announce(8479, version="1.0.3", tv="10.0.1.9", host="tv-xiaomi")

    assert one.name != two.name
    assert one.name == f"torrcast-tv-samsung.{SERVICE}"
    assert two.name.endswith(SERVICE)


def test_leaving_an_unopened_announcement_is_quiet() -> None:
    # Мост, которому сеть не дала объявиться, всё равно уходит без исключения.
    Announce(8479, version="1.0.3", tv="", host="stand").close()


def test_the_anchor_is_never_an_address_of_this_house() -> None:
    # Якорь спрашивает у ядра, каким адресом нас видно, когда телевизор не назван.
    # Свой он быть не вправе: тогда ответом был бы адрес петли.
    assert ANCHOR.startswith("192.0.2.")
