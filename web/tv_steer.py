"""Пульт каста «На ТВ»: переключатель и перемотка идут прямо приёмнику ТВ.

🔴 Показ вкладки, отданный на ТВ, остаётся показом вкладки: файл-пульт юнита показа
(:mod:`hass.say`) достаётся её приёмнику, а тот пульта не берёт (TC-1210). Телевизор при
этом держит страница (:mod:`web.tv_session`), и командовать им может только она. Пока
команду слали юниту, браузер на время каста переставал быть пультом вовсе: пауза и
перемотка с панели плеера отвечали ``no_remote``, хотя картину уже играл ТВ.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from torrcast.domain.position import Position
from torrcast.ports.receiver import Receiver


@runtime_checkable
class _Steerable(Protocol):
    """Приёмник, которым можно управлять как с пульта (тот же набор, что у юнита показа)."""

    def seek(self, pos: float) -> None: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...


def tv_steer(receiver: Receiver, heard: Position | None, command: str, arg: float) -> bool:
    """Исполнить ``toggle`` или ``seekby`` на приёмнике ТВ; не умеет - ``False``.

    Перемотка считается от ПОСЛЕДНЕГО УСЛЫШАННОГО опроса: свежее чтение на излёте бывает
    старше него (:meth:`web.tv_session.TvSession.stop`). Переключателю, наоборот, нужно
    слово приёмника про сейчас: два нажатия подряд внутри одного такта опроса иначе
    оба ставили бы паузу.
    """
    if not isinstance(receiver, _Steerable):
        return False
    if command == "seekby":
        spot = heard if heard is not None else receiver.position()
        receiver.seek(max(0.0, spot.pos + arg))
    elif receiver.position().playing:
        receiver.pause()
    else:
        receiver.resume()
    return True
