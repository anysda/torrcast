"""Штатный конец показа по SIGTERM от ``cast stop``.
Ставит обработчик юнит показа, ловит его :func:`torrcast.commands.main`.
"""

from __future__ import annotations

__all__ = ["_Stopped", "_on_term"]


class _Stopped(KeyboardInterrupt):
    """``cast stop``: SIGTERM пришёл, показ окончен штатно — это не авария.

    Наследуемся от ``KeyboardInterrupt`` намеренно: раскрутка обязана пройти ровно так
    же, как проходила, — через ``finally`` в :func:`_play`, где пишется позиция, гаснет
    упаковка и снимается каст. Меняется только вывеска на выходе: ``cast stop`` — это
    успех, и юнит обязан умереть кодом 0, иначе systemd помечает его ``failed`` и после
    каждой штатной остановки в `systemctl` краснеет `● torrcast-play … failed`.
    """


def _on_term(_signal: int, _frame: object) -> None:
    raise _Stopped
