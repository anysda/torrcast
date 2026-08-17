"""Юнит показа как объект: transient-юнит systemd за портом :mod:`torrcast.ports.show_unit`.

Своего кода тут нет ни строчки - разговор с systemd живёт в соседних модулях
:mod:`torrcast.adapters.systemd`, а этот класс только называет их именами договора.
Ставит его композиционный корень (:mod:`torrcast.runtime.wire`).
"""

from torrcast.adapters.systemd.stop_play_unit import stop_play_unit
from torrcast.adapters.systemd.unit_active import unit_active
from torrcast.adapters.systemd.unit_key import unit_key
from torrcast.adapters.systemd.unit_why import unit_why


class TransientShowUnit:
    """Показ, идущий в transient-юните ``torrcast-play``."""

    def active(self) -> bool:
        """Идёт ли показ прямо сейчас."""
        return bool(unit_active())

    def why(self) -> str:
        """Последняя внятная строка самого показа из journald."""
        return str(unit_why())

    def stop(self) -> None:
        """Погасить юнит и дождаться его смерти: по SIGTERM сторож допишет позицию."""
        stop_play_unit()

    def key(self) -> str:
        """Ключ состояния играющего показа - из ``--description`` юнита."""
        return str(unit_key())
