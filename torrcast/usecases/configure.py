"""Выбирает телевизор и сохраняет настройку приёмника."""

from dataclasses import replace
from typing import Literal

from torrcast.domain.catalogs.phrase import phrase
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
    ровно в том, откуда взялась строка. Этим же сценарием установка подхватывает
    приёмник сама: отдельного шага «после установки позови ``cast --tv``» нет.

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
        note = phrase("configure.headless_note") if device.address == "mock" else ""
        name = f"{device.name} - " if device.name else ""
        self._console.write(
            phrase("configure.tv_line", name=name, address=device.address, note=note)
        )
        return EXIT_OK

    def _found_tv(self) -> ReceiverInfo:
        """``cast --tv`` без адреса: найти приёмники в сети и взять своего.

        Это последний шаг установки, и человек на нём знает про свой дом ровно одно - как
        телевизор называется. Поэтому найденный ОДИН приёмник не спрашивается вовсе:
        единственный приёмник в своей сети - он и есть телевизор, и вопрос тут был бы
        ручкой ради ручки. Вопрос остаётся ровно там, где выбор по-настоящему есть:
        приёмников несколько - список из имён и адресов, ответ номером.

        Никого не нашли - не «ошибка сети», а понятная причина: телевизор выключен или
        стоит в другой сети. Нашли несколько, а терминала нет - отказываемся вслух, ровно
        как в меню картин: выбрать вслепую тут значит записать в конфиг чужое устройство.
        """
        devices = self._finder.find()
        for note in self._finder.notes():
            self._console.write(note)
        if not devices:
            raise NotFoundError(phrase("configure.no_receivers_found"))
        if len(devices) == 1:
            return devices[0]
        self._console.write(self._lines(devices))
        if not self._console.interactive():
            raise NotFoundError(phrase("configure.found_no_terminal", count=len(devices)))
        return devices[self._console.choose(phrase("configure.which_tv"), len(devices)) - 1]

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
