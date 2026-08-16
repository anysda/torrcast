"""Проверяет поиск приёмника на подставленном discovery."""

from types import SimpleNamespace

from torrcast.adapters.chromecast.py_chromecast_receiver_finder import PyChromecastReceiverFinder


def test_maps_and_filters_discovered_receivers() -> None:
    browser = SimpleNamespace(stop_discovery=lambda: None)
    casts = [SimpleNamespace(name="Гостиная", host="10.0.0.2", model_name="TV")]
    finder = PyChromecastReceiverFinder(lambda **_kwargs: (casts, browser))

    found = finder.find("гостиная")

    assert [(item.name, item.address, item.model) for item in found] == [
        ("Гостиная", "10.0.0.2", "TV")
    ]
