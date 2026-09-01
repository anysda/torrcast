"""Задание показа как объект: задание launchd за портом :mod:`torrcast.ports.show_unit`.

Своего кода тут нет ни строчки - разговор с launchd живёт в соседних модулях
:mod:`torrcast.adapters.launchd`, а этот класс только называет их именами договора.
Ставит его композиционный корень (:mod:`torrcast.runtime.wire`).
"""

from collections.abc import Callable

from torrcast.adapters.launchd.job_active import job_active
from torrcast.adapters.launchd.job_key import job_key
from torrcast.adapters.launchd.job_why import job_why
from torrcast.adapters.launchd.stop_play_job import stop_play_job


class LaunchdShowUnit:
    """Показ, идущий заданием launchd ``torrcast-play``.

    Четыре системные операции приезжают заводом: боевые умолчания - соседи по пакету,
    так что корень собирает его по-прежнему одним ``LaunchdShowUnit()``. Стенду они
    нужны поимённо, чтобы проверять развод имён договора по операциям, не зная, из
    какого модуля какая приехала.
    """

    def __init__(
        self,
        *,
        active: Callable[[], object] = job_active,
        why: Callable[[], object] = job_why,
        key: Callable[[], object] = job_key,
        stop: Callable[[], object] = stop_play_job,
    ) -> None:
        self._active = active
        self._why = why
        self._key = key
        self._stop = stop

    def active(self) -> bool:
        """Идёт ли показ прямо сейчас."""
        return bool(self._active())

    def why(self) -> str:
        """Последняя внятная строка самого показа из журнала задания."""
        return str(self._why())

    def stop(self) -> None:
        """Погасить задание и дождаться его смерти: по SIGTERM сторож допишет позицию."""
        self._stop()

    def key(self) -> str:
        """Ключ состояния играющего показа - из окружения живого задания."""
        return str(self._key())
