"""Поиск приёмников отдаёт список и отдельно - пояснения о пропущенных подсетях."""

from torrcast.adapters.chromecast.network_receiver_finder import NetworkReceiverFinder
from torrcast.adapters.chromecast.scan import Device, Found


def test_devices_and_notes_arrive_separately() -> None:
    found = Found(
        devices=[Device("10.0.0.50", name="Samsung Q70D"), Device("10.0.0.60", model="Chromecast")],
        notes=["подсеть 10.5.0.0/16 на 65534 адресов"],
    )
    finder = NetworkReceiverFinder(lambda: found)

    devices = finder.find()

    assert [(item.name, item.address, item.model) for item in devices] == [
        ("Samsung Q70D", "10.0.0.50", ""),
        ("", "10.0.0.60", "Chromecast"),
    ]
    assert finder.notes() == ["подсеть 10.5.0.0/16 на 65534 адресов"]


def test_a_named_search_keeps_only_its_receiver() -> None:
    found = Found(devices=[Device("10.0.0.50", name="Гостиная"), Device("10.0.0.60", name="Кухня")])

    assert [item.address for item in NetworkReceiverFinder(lambda: found).find("гостиная")] == [
        "10.0.0.50"
    ]


def test_nothing_found_means_no_notes_either() -> None:
    assert NetworkReceiverFinder(lambda: Found()).notes() == []
