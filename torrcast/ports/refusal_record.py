"""Порт записи о несостоявшемся подъёме показа: договорное слово отказа и его срок.

Подъём показа кончается отказом в разных местах и в РАЗНЫХ процессах: молчание службы
раздач видит командная строка (:func:`torrcast.cli.answered.answered`), а отказ
приёмника и нечитаемый источник - юнит показа
(:func:`torrcast.usecases.playback._show_blame._blame_the_end`). Отвечает же странице мост
(:meth:`hass.bridge.Bridge.state`). Чтобы эти места не знали друг о друге, слово отказа
(:mod:`torrcast.domain.start_refusal`) пишется в порт, а куда оно пишется на самом деле,
решает композиционный корень (:func:`torrcast.runtime.wire.wire`): боевой ответ -
файл рядом с состоянием, общий для обоих процессов
(:mod:`torrcast.adapters.filesystem.state.file_refusal_record`).

Срок у записи тот же, что у словесного отказа моста (:attr:`hass.orders.Orders.last_error`):
прошлый отказ живёт до начала следующего показа. Стирает запись взятие нового поручения
(:meth:`hass.orders.Orders.take`), а не чтение: опрос страницы идёт раз в две секунды, и
стёртая первым же опросом запись не дожила бы до второго.
"""

from __future__ import annotations


class RefusalRecord:
    """Куда пишется слово последнего отказа подъёма. Умолчание - молчание.

    До слова композиционного корня писать некуда, и отказ говорится только в консоль -
    тот же расклад, что у следа (:class:`torrcast.ports.journal.silent.Silent`).
    """

    def record(self, reason: str) -> None:
        """Запомнить договорное слово отказа; пустое слово не записывается вовсе."""

    def read(self) -> str | None:
        """Слово последнего отказа; его не было или писать некуда - ``None``."""
        return None

    def forget(self) -> None:
        """Стереть запись: новый подъём взят в работу, прошлый отказ ему не принадлежит."""


class _Slot:
    """Кто держит запись об отказе этого процесса. До слова корня - молчание."""

    def __init__(self) -> None:
        self._kept: RefusalRecord = RefusalRecord()

    def current(self) -> RefusalRecord:
        """Куда пишется и откуда читается слово отказа прямо сейчас."""
        return self._kept

    def install(self, kept: RefusalRecord) -> None:
        """Назначить держателя записи. Зовёт это композиционный корень и тесты."""
        self._kept = kept


#: Порт - состояние ПРОЦЕССА, а не объект, который носят по вызовам: слот один на прогон.
_slot = _Slot()
#: Прежние имена слоёв: их зовут отовсюду, и функциями они и остаются.
refusal_record = _slot.current
install = _slot.install

__all__ = ["RefusalRecord", "install", "refusal_record"]
