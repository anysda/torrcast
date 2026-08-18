"""Слот назначенного юнита показа: кто играет прямо сейчас и кто это назначает."""

from torrcast.ports.show_unit.idle import Idle
from torrcast.ports.show_unit.show_unit import ShowUnit


class Slot:
    """Юнит показа, назначенный на этот процесс. До слова корня в слоте пусто."""

    def __init__(self) -> None:
        self._unit: ShowUnit = Idle()

    def current(self) -> ShowUnit:
        """Юнит показа, назначенный на этот процесс."""
        return self._unit

    def install(self, target: ShowUnit) -> None:
        """Назначить юнит показа. Зовёт это композиционный корень и тесты."""
        self._unit = target


#: Порт - состояние ПРОЦЕССА, а не объект, который носят по вызовам: слот один на прогон.
_slot = Slot()
#: Прежние имена слоёв: их зовут отовсюду, и функциями они и остаются.
unit = _slot.current
install = _slot.install
