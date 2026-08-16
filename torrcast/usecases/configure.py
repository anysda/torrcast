"""Выбирает телевизор и сохраняет настройку приёмника."""

from dataclasses import replace
from typing import Literal

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.receiver_info import ReceiverInfo
from torrcast.ports.configuration_store import ConfigurationStore
from torrcast.ports.console import Console
from torrcast.ports.receiver_finder import ReceiverFinder


class Configure:
    """Сценарий команды ``cast --tv``."""

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
        return 0

    def _found_tv(self) -> ReceiverInfo:
        devices = self._finder.find()
        if not devices:
            raise NotFoundError(
                "приёмников в сети не нашёл - телевизор включён и в той же сети? "
                "адрес можно задать и руками: cast --tv <ip>"
            )
        self._console.write(
            "\n".join(
                f"  {number}. {device.name or device.model} - {device.address}"
                for number, device in enumerate(devices, start=1)
            )
        )
        answer = self._console.ask("Какой телевизор?", str(len(devices)))
        try:
            return devices[int(answer) - 1]
        except (ValueError, IndexError):
            return devices[-1]
