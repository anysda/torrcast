"""Юнит показа как объект: transient-юнит systemd за портом :mod:`torrcast.ports.show_unit`.

Своего кода тут нет ни строчки - разговор с systemd живёт в соседних модулях
:mod:`torrcast.adapters.systemd`, а этот класс только называет их именами договора.
Ставит его композиционный корень (:mod:`torrcast.runtime.wire`).
"""

from collections.abc import Callable

from torrcast.adapters.systemd.stop_play_unit import stop_play_unit
from torrcast.adapters.systemd.unit_active import unit_active
from torrcast.adapters.systemd.unit_key import unit_key
from torrcast.adapters.systemd.unit_why import unit_why


class TransientShowUnit:
    """Показ, идущий в transient-юните ``torrcast-play``.

    Четыре системные операции приезжают заводом: боевые умолчания - соседи по пакету,
    так что корень собирает его по-прежнему одним ``TransientShowUnit()``. Стенду они
    нужны поимённо, чтобы проверять развод имён договора по операциям, не зная, из
    какого модуля какая приехала.
    """

    def __init__(
        self,
        *,
        active: Callable[[], object] = unit_active,
        why: Callable[[], object] = unit_why,
        key: Callable[[], object] = unit_key,
        stop: Callable[[], object] = stop_play_unit,
    ) -> None:
        self._active = active
        self._why = why
        self._key = key
        self._stop = stop

    def active(self) -> bool:
        """Идёт ли показ прямо сейчас."""
        return bool(self._active())

    def why(self) -> str:
        """Последняя внятная строка самого показа из journald."""
        return str(self._why())

    def stop(self) -> None:
        """Погасить юнит и дождаться его смерти: по SIGTERM сторож допишет позицию."""
        self._stop()

    def key(self) -> str:
        """Ключ состояния играющего показа - из ``--description`` юнита."""
        return str(self._key())
