"""Проверяет системную среду прогрева."""

from typing import Any

import pytest

from torrcast.adapters.warm_environment import environment


def test_warm_environment_has_monotonic_clock() -> None:
    """Монотонные часы доступны через адаптер."""
    assert environment.monotonic() >= 0


def test_the_media_tract_is_taken_from_the_facade_at_every_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Упаковку и пробный прогон среда спрашивает у фасада именем, а не держит у себя.

    На этом стоят все подмены медиатракта в зеркалах прогрева. Сценарий читает не
    ``torrcast.stream``, а слоты :mod:`torrcast.usecases.warm._state`, и лежат в них методы
    среды: сравнение ``is`` со ``stream.pack_start`` даёт False. Из этого False уже
    делали вывод «подмена мёртвая» (TC-666), хотя живая она ровно потому, что среда на
    каждом вызове идёт за именем на фасад.

    🔴 Связать имя на сборке (``pack_start = staticmethod(stream.pack_start)``) или
    увести адрес мимо фасада (``import_module("torrcast.stream_pack")``) - и шесть подмен
    в зеркалах прогрева замолчат разом. Замер пробой: такую поломку адреса видит одно
    зеркало прогрева из четырёх, остальные три остаются зелёными. Поэтому адрес держится
    мерой, а не договорённостью.
    """
    from torrcast import stream

    class _Sentinel:
        @classmethod
        def start(cls, *args: object, **kwargs: object) -> str:
            return "упаковка с фасада"

    monkeypatch.setattr(stream, "pack_start", lambda *args, **kwargs: "начало с фасада")
    monkeypatch.setattr(stream, "Packer", _Sentinel)
    packer: Any = environment.packer_type

    assert environment.pack_start("нет", 0.0) == "начало с фасада"
    assert packer.start() == "упаковка с фасада"
