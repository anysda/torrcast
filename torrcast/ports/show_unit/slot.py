"""Слот назначенного юнита показа: кто играет прямо сейчас и кто это назначает."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.ports.show_unit.show_unit import ShowUnit


class Slot:
    """Юнит показа, назначенный на этот процесс. Пока его не назначили, слот пуст."""

    def __init__(self) -> None:
        self._unit: ShowUnit | None = None

    def current(self) -> ShowUnit:
        """Юнит показа, назначенный на этот процесс.

        Пустой слот отказывает, а не отвечает «ничего не играет»: этот ответ - не
        отсутствие юнита, а утверждение о нём, и врёт он в обе стороны сразу. По нему
        уборка считает раздачу под живым показом сиротой и сносит её
        (:func:`torrcast.usecases.torrents.forget`), а запуск не гасит предыдущий показ и
        заводит второй поверх играющего. Отказ приходит на первом же вопросе о юните.
        """
        if self._unit is None:
            raise RuntimeError(phrase("ports.show_unit_not_installed"))
        return self._unit

    def install(self, target: ShowUnit) -> None:
        """Назначить юнит показа. Зовёт это композиционный корень и тесты."""
        self._unit = target


#: Порт - состояние ПРОЦЕССА, а не объект, который носят по вызовам: слот один на прогон.
_slot = Slot()
#: Прежние имена слоёв: их зовут отовсюду, и функциями они и остаются.
unit = _slot.current
install = _slot.install
