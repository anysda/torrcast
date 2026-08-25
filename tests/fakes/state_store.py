"""Держит состояние просмотра в памяти теста вместо файла на диске."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState


class FakeStateStore:
    """Состояние на один прогон: помнит позицию, но файлов на диске не заводит.

    Ставится на порт состояния (:mod:`torrcast.ports.state_store`) тестом, который
    просит память вслух. Умолчанием порта оно быть не может: молча забытая закладка
    неотличима от сохранённой, пока зритель не вернётся к недосмотренному.

    Позицию оно всё же помнит, а не отвечает пустотой: сторож показа спрашивает её на
    каждом тике, и с пустым ответом «досмотрено» не наступало бы никогда.
    """

    def __init__(self) -> None:
        self._entries: dict[str, Entry] = {}

    def load(self) -> WatchState:
        """Своё состояние на каждое чтение, а не общий изменяемый объект.

        Файловое хранилище отдаёт новое значение всякий раз, и подделка обязана врать
        так же: иначе правка без :meth:`save` доезжала бы до соседа сама собой, и тест
        зеленел бы на записи, которой боевой путь не делает.
        """
        return WatchState(dict(self._entries))

    def save(self, state: WatchState) -> None:
        self._entries = dict(state.entries)
