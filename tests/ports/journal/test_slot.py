"""Слот назначенного писателя следа: кто пишет прямо сейчас и кто это назначает."""

from torrcast.ports.journal.journal import Journal
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import Slot, install, journal
from torrcast.ports.json_value import JsonValue


class _Spy(Silent):
    def __init__(self) -> None:
        self.seen: list[str] = []

    def mark(self, name: str, **facts: JsonValue) -> None:
        self.seen.append(name)


def test_a_fresh_slot_is_silent_until_the_root_says_otherwise() -> None:
    """До слова композиционного корня в слоте лежит молчание, а не пустота."""
    slot = Slot()

    assert isinstance(slot.current(), Silent)


def test_the_installed_sink_is_what_the_layers_get() -> None:
    """Назначенное слоям и отдаётся: имена слоёв смотрят в тот же слот."""
    spy = _Spy()
    install(spy)

    port: Journal = journal()
    port.mark("старт")

    assert spy.seen == ["старт"]
    assert journal() is spy


def test_the_public_name_is_a_function_and_not_the_module_beside_it() -> None:
    """Отрицательная проба: в пакете рядом лежит модуль с тем же именем.

    ``torrcast.ports.journal.journal`` - это и модуль договора, и имя, которым слои зовут
    назначенного писателя. Порядок реэкспорта в ``__init__`` решает, что из двух достанется
    читателю, и ошибка тут молчаливая: слои получили бы модуль и упали бы уже на вызове.
    """
    assert callable(journal), "имя следа перекрыто модулем рядом"
    assert isinstance(journal(), Silent | object)
