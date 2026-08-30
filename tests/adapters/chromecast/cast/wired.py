"""Приёмник без сети для зеркал пакета: подставное устройство вместо pychromecast.

Всё остальное в нём настоящее - сторож подвиса, счёт смертей, ожидание картинки, - и
проверяется именно оно. Подменять ручки у общего класса нельзя: подмена дожила бы до
соседнего теста, поэтому она конструкторская.
"""

from __future__ import annotations

from typing import Any

from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver


class Status:
    """MEDIA_STATUS, как его отдаёт приёмник: позиция, состояние, причина простоя."""

    def __init__(
        self,
        pos: float = 0.0,
        state: str = "PLAYING",
        idle_reason: str | None = None,
        duration: float = 5977.0,
    ) -> None:
        self.current_time = pos
        self.player_state = state
        self.idle_reason = idle_reason
        self.duration = duration
        self.player_is_playing = state in {"PLAYING", "BUFFERING"}
        self.content_id = ""


class Controller:
    """Медиаконтроллер устройства: запоминает прыжки и команды вместо сети."""

    def __init__(self, status: Status | None = None) -> None:
        self.status = status if status is not None else Status()
        self.jumps: list[float] = []
        self.said: list[str] = []

    def seek(self, pos: float) -> None:
        self.jumps.append(pos)

    def stop(self) -> None:
        self.said.append("stop")

    def pause(self) -> None:
        self.said.append("pause")

    def play(self) -> None:
        self.said.append("play")


class Device:
    """Устройство приёмника: приложение на экране, сессия и медиаконтроллер."""

    def __init__(self, app: str = "CC1AD845", session: str = "наша") -> None:
        self.media_controller = Controller()
        self.status = _Screen(app, session)
        self.said: list[str] = []

    def quit_app(self) -> None:
        self.said.append("quit_app")

    def disconnect(self) -> None:
        self.said.append("disconnect")


class _Screen:
    """RECEIVER_STATUS: что за приложение на экране и чья это сессия."""

    def __init__(self, app: str, session: str) -> None:
        self.app_id = app
        self.session_id = session


class Wired(ChromecastReceiver):
    """Живой приёмник, у которого вместо сети - подставное устройство."""

    def __init__(self, device: Device | None = None, address: str = "10.0.0.50", **rest: Any):
        super().__init__(address, **rest)
        self.device = device if device is not None else Device()
        #: Соединение считается уже поднятым: сеть тут подменена целиком.
        self._cast = self.device

    def _device(self) -> Any:
        self._cast = self.device  # как настоящий подъём соединения, только без сети
        return self.device


class Quiet(Wired):
    """Приёмник, у которого подъём приложения и ожидание картинки только записываются.

    Тремя ручками он разыгрывает все три исхода несостоявшегося подъёма: чужой показ на
    экране (``device``), легшее соединение (``breaks``) и ушедший LOAD без картинки
    (``settles``). Стоит в общем инвентаре, а не в одном зеркале, затем, что сличать по
    нему приходится ДВА тракта: живой и сухой (:class:`_Blaming`), и вторая копия этой
    подделки развела бы их ровно там, где их и надо держать вместе.
    """

    def __init__(self, settles: bool = True, breaks: bool = False, **rest: Any) -> None:
        super().__init__(**rest)
        self.settles = settles
        self.breaks = breaks
        self.loads: list[float] = []
        self.paused_loads: list[bool] = []
        self.budgets: list[float] = []
        self.restarts = 0

    def _restart_app(self) -> None:
        self.restarts += 1
        if self.breaks:
            raise OSError("приёмника нет в сети")

    def _load(self, at: float = 0.0, paused: bool = False) -> None:
        self.loads.append(at)
        self.paused_loads.append(paused)

    def _settle(self, budget: float) -> bool:
        self.budgets.append(budget)
        return self.settles
