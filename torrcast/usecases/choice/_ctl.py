"""Диагностический пульт: одноразовая команда показу из файла."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from torrcast.usecases.choice.configure import _environment_port

if TYPE_CHECKING:
    from torrcast.ports.choice_types import Receiver


@runtime_checkable
class _Revivable(Protocol):
    """Приёмник, чей погасший показ можно поднять заново (:class:`_Revival`).

    Отдельно от :class:`Receiver` намеренно: воскрешать имеет смысл только тот приёмник,
    у которого есть собственное терпение и который его тратит. Терпение mock моделирует
    нарочно и по замерам живого ТВ (:attr:`torrcast.cast.MockReceiver.PATIENCE`) - иначе
    целый класс аварий «источник моргнул» уходил бы из-под сухих прогонов вовсе.

    ``replay`` отвечает секундой, С КОТОРОЙ показ пошёл, а не «да/нет»: приёмник вправе
    поднять его не там, где просили (:meth:`torrcast.cast.ChromecastReceiver._past_deadly`),
    и тогда «да» на месте, которого зритель не увидит, - это враньё о пятнадцати секундах
    фильма. :data:`torrcast.domain.not_raised.NOT_RAISED` - картинки нет; ноль ответом об отказе
    не является, это законное начало картины.
    """

    def replay(self, at: float) -> float: ...


@runtime_checkable
class _Steerable(Protocol):
    """Приёмник, которым можно управлять как с пульта (:data:`CTL_ENV`)."""

    def seek(self, pos: float) -> None: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...


def _ctl(receiver: Receiver) -> None:
    """Исполнить команду диагностического пульта, если она положена (:data:`CTL_ENV`).

    Файл съедается до исполнения: команда одноразовая, и повторить её на следующем опросе
    нельзя даже при осечке приёмника — иначе одна опечатка мотала бы фильм вечно.
    """
    line = _environment_port().read_command()
    if line is None or not isinstance(receiver, _Steerable):
        return
    if not line:
        return
    word, _, rest = line.partition(" ")
    _environment_port().write(f"пульт: {line}")
    with contextlib.suppress(Exception):
        if word == "seek":
            receiver.seek(float(rest))
        elif word == "pause":
            receiver.pause()
        elif word == "play":
            receiver.resume()
