"""Слот назначенного индикатора: чем рисуется ход и кто это назначает."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.ports.progress.progress import Progress
from torrcast.ports.progress.quiet import Quiet


class Slot:
    """Чем рисуется ход прямо сейчас. В слоте лежит ЗАВОД индикатора, а не индикатор.

    Разница не бухгалтерская: индикатор заводится на фазу работы, а не один на процесс,
    и два вызова обязаны дать два разных объекта - иначе вложенная фаза гасила бы
    внешнюю своим ``stop``.
    """

    def __init__(self) -> None:
        self._factory: Callable[[], Progress] = Quiet

    def new(self) -> Progress:
        """Новый индикатор: по одному на фазу работы, а не один на процесс."""
        return self._factory()

    def factory(self) -> Callable[[], Progress]:
        """Чем сейчас рисуется ход: нужно тому, кто ставит своё и обязан вернуть чужое."""
        return self._factory

    def install(self, factory: Callable[[], Progress]) -> None:
        """Назначить, чем показывать ход. Зовёт это композиционный корень и тесты."""
        self._factory = factory


#: Порт - состояние ПРОЦЕССА, а не объект, который носят по вызовам: слот один на прогон.
_slot = Slot()
#: Прежние имена слоёв: их зовут отовсюду, и функциями они и остаются.
progress = _slot.new
factory = _slot.factory
install = _slot.install
