"""Выбирает телевизор и сохраняет настройку приёмника."""

from dataclasses import replace
from typing import Literal

from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.receiver_info import ReceiverInfo
from torrcast.ports.configuration_store import ConfigurationStore
from torrcast.ports.console import Console
from torrcast.ports.receiver_finder import ReceiverFinder


class Configure:
    """Сценарий команды ``cast --tv``: единственная настройка - адрес телевизора.

    Без адреса приёмники ищутся сами, с адресом - берётся сказанное: кто свой IP помнит,
    тому лишний поиск ни к чему. Пишется в конфиг в обоих случаях одинаково, разница
    ровно в том, откуда взялась строка.

    Отдельное значение ``mock`` включает headless-приёмник: так torrcast проверяется без
    телевизора, и адрес ТВ в конфиге при этом отсутствует физически.
    """

    def __init__(self, store: ConfigurationStore, finder: ReceiverFinder, console: Console) -> None:
        self._store = store
        self._finder = finder
        self._console = console

    def run(self, address: str | None = None) -> int:
        """Сохраняет названный адрес либо выбранный найденный приёмник."""
        device = ReceiverInfo(name="", address=address) if address is not None else self._found_tv()
        receiver: Literal["chromecast", "mock"] = (
            "mock" if device.address == "mock" else "chromecast"
        )
        settings = replace(self._store.load(), tv=device.address, receiver=receiver)
        self._store.save(settings)
        note = " (headless-приёмник, каста наружу нет)" if device.address == "mock" else ""
        name = f"{device.name} - " if device.name else ""
        self._console.write(f"ТВ: {name}{device.address}{note}")
        return EXIT_OK

    def _found_tv(self) -> ReceiverInfo:
        """``cast --tv`` без адреса: найти приёмники в сети и спросить, который из них ТВ.

        Это последний шаг установки, и человек на нём знает про свой дом ровно одно - как
        телевизор называется. Поэтому список из имён и адресов, ответ номером, а
        единственный найденный подтверждается пустым Enter.

        Никого не нашли - не «ошибка сети», а понятная причина: телевизор выключен или
        стоит в другой сети. Нашли несколько, а терминала нет - отказываемся вслух, ровно
        как в меню картин: выбрать вслепую тут значит записать в конфиг чужое устройство.
        """
        devices = self._finder.find()
        for note in self._finder.notes():
            self._console.write(note)
        if not devices:
            raise NotFoundError(
                "приёмников в сети не нашёл - телевизор включён и в той же сети? "
                "адрес можно задать и руками: cast --tv <ip>"
            )
        self._console.write(self._lines(devices))
        if len(devices) > 1 and not self._console.interactive():
            raise NotFoundError(
                f"нашёл приёмников: {len(devices)}, а терминала нет - вслепую не выбираю; "
                "назови адрес сам: cast --tv <ip>"
            )
        return devices[self._console.choose("Какой телевизор?", len(devices)) - 1]

    @staticmethod
    def _lines(devices: list[ReceiverInfo]) -> str:
        """Список найденных приёмников: номер, имя, адрес - по строке на устройство.

        Формат тот же, что у меню картин: глаз уже знает, что отвечать надо номером
        слева. Адрес печатается всегда, даже когда имя есть: имён вида «Гостиная» в доме
        бывает два, а адрес различает их наверняка.
        """
        return "\n".join(
            f"  {number}. {device.title} - {device.address}"
            for number, device in enumerate(devices, start=1)
        )
