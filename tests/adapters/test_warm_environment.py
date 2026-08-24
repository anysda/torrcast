"""Проверяет системную среду прогрева."""

from typing import Any

import pytest

from torrcast.adapters import warm_environment
from torrcast.adapters.warm_environment import environment


def test_warm_environment_has_monotonic_clock() -> None:
    """Монотонные часы доступны через адаптер."""
    assert environment.monotonic() >= 0


def test_the_media_tract_is_taken_from_its_slot_at_every_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Медиатракт среда спрашивает на каждом вызове, а не связывает на сборке класса.

    На этом стоят все подмены медиатракта в зеркалах прогрева. Сценарий читает не свои
    имена, а слоты :mod:`torrcast.usecases.warm._state`, и лежат в них методы среды:
    сравнение ``is`` с исходной функцией даёт False. Из этого False уже делали вывод
    «подмена мёртвая» (TC-666), хотя живая она ровно потому, что среда на каждом вызове
    идёт за именем в свой модульный слот.

    🔴 Связать имя на сборке (``settle_start = staticmethod(...)``) - и подмены в
    зеркалах прогрева замолчат разом. Замер пробой: такую поломку адреса видит одно
    зеркало прогрева из четырёх, остальные три остаются зелёными. Поэтому адрес держится
    мерой, а не договорённостью.

    Упаковщик (:class:`Packer`) переехал в медиатракт и адаптеру доступен по имени, но
    имя это среда читает так же поздно - из своего модуля; мера сторожит и его.
    """

    class _Sentinel:
        @classmethod
        def start(cls, *args: object, **kwargs: object) -> str:
            return "упаковка из медиатракта"

    monkeypatch.setattr(warm_environment, "_settle_start", lambda url, at: (41.0, 42.5))
    monkeypatch.setattr(warm_environment, "_segment_name", lambda slot: "имя из слота")
    monkeypatch.setattr(warm_environment, "_segment_slot", lambda name: 77)
    monkeypatch.setattr(warm_environment, "_pack_command", lambda *a, **k: ["команда из слота"])
    monkeypatch.setattr(warm_environment, "Packer", _Sentinel)
    packer: Any = environment.packer_type

    assert environment.settle_start("нет", 0.0) == (41.0, 42.5)
    assert environment.segment_name(0) == "имя из слота"
    assert environment.segment_slot("нет") == 77
    assert environment.pack_command() == ["команда из слота"]
    assert packer.start() == "упаковка из медиатракта"
