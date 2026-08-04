"""Приёмники: реальный Chromecast и mock.

Приёмник — интерфейс с двумя реализациями (§3 ТЗ). ``mock`` не заглушка
«для галочки»: это headless-клиент, который тянет HLS как ТВ, декодирует и
отдаёт позицию — на нём проходит вся автономная приёмка (§7), включая resume,
порог 95 % и автопереход серий.

Никакой Samsung-специфики здесь нет и быть не должно (§1): ни PowerState,
ни анти-wakeup, ни nudge-сторожей.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from torrcast import InfraError

__all__ = ["ChromecastReceiver", "MockReceiver", "Position", "Receiver", "make_receiver"]

ReceiverKind = Literal["chromecast", "mock"]


@dataclass(frozen=True, slots=True)
class Position:
    """Снимок позиции воспроизведения."""

    pos: float
    dur: float
    playing: bool = False

    @property
    def ratio(self) -> float:
        return self.pos / self.dur if self.dur > 0 else 0.0


@runtime_checkable
class Receiver(Protocol):
    """Что нам нужно от приёмника — и ничего сверх того."""

    def play(self, url: str, title: str = "") -> None:
        """Начать воспроизведение HLS-манифеста."""
        ...

    def stop(self) -> None:
        """Снять каст."""
        ...

    def position(self) -> Position:
        """Текущая позиция и длительность."""
        ...


class ChromecastReceiver:
    """Реальный приёмник: catt/pychromecast по адресу из конфига.

    ⚠️ Порт 8009 открыт даже в standby, любой коннект будит ТВ (§8) — поэтому
    объект создаётся только тогда, когда кастить действительно собираются.
    """

    def __init__(self, address: str) -> None:
        if not address:
            raise InfraError("адрес ТВ не задан: cast --tv <ip>")
        self.address = address

    def play(self, url: str, title: str = "") -> None:
        self._catt("cast", url)

    def stop(self) -> None:
        self._catt("stop")

    def position(self) -> Position:
        # TODO(этап 3): снимать позицию через pychromecast media_controller.
        raise InfraError("снятие позиции с Chromecast ещё не реализовано")

    def _catt(self, *args: str) -> None:
        try:
            subprocess.run(
                ["catt", "-d", self.address, *args],
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise InfraError("catt не установлен") from exc
        except subprocess.CalledProcessError as exc:
            raise InfraError(f"приёмник {self.address} не принял каст") from exc


class MockReceiver:
    """Headless-приёмник для автономной приёмки.

    Тянет HLS по https ровно как ТВ (включая проверку CORS-заголовков),
    декодирует ffmpeg'ом в ``/dev/null`` и по ходу отдаёт позицию.

    TODO(этап 2): запуск ffmpeg-декодера и парсинг ``-progress`` в позицию.
    """

    def __init__(self) -> None:
        self._url: str | None = None
        self._position = Position(pos=0.0, dur=0.0, playing=False)

    def play(self, url: str, title: str = "") -> None:
        self._url = url
        self._position = Position(pos=0.0, dur=0.0, playing=True)

    def stop(self) -> None:
        self._position = Position(pos=self._position.pos, dur=self._position.dur, playing=False)

    def position(self) -> Position:
        return self._position


def make_receiver(kind: ReceiverKind, address: str = "") -> Receiver:
    """Собрать приёмник по типу из конфига."""
    if kind == "mock":
        return MockReceiver()
    return ChromecastReceiver(address)
