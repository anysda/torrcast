"""Паспорт файла, который показ дочитывает сам, когда картинка уже на экране.

Заводит его показ (:func:`torrcast.usecases.playback._play._play`), пускает в чтение конец
картинки (:meth:`torrcast.usecases.playback._ending._Ending.tick`) после первого кадра.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future
from typing import Final

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.media import Media

#: Сколько ждать голову паспорта: её куски у службы раздач уже лежат - их только что читал
#: отбор раздачи, - и чтение их за секунду. Хвост ждётся сверх неё своим бюджетом щупа.
END_HEAD: Final = 20.0


class _Ahead(Future[Media]):
    """Паспорт ``source``, который читается только по :meth:`go` и только один раз.

    🔴 До первого кадра паспорт не читается: стенд 10-10, «Теория большого взрыва» s2e5,
    холодный рой - голова и хвост файла делили службу раздач с заходом упаковки, и вход
    показа ждал 16.7 с против 7.2 с без них, закончившись ровно тогда же, когда хвост.
    """

    def __init__(self, source: str) -> None:
        super().__init__()
        self._source = source
        self._gate = threading.Lock()
        self._going = False

    def go(self) -> None:
        """Пустить чтение в фоне; повторный зов ничего не делает."""
        with self._gate:
            if self._going:
                return
            self._going = True
        threading.Thread(target=self._read, name="end-ahead", daemon=True).start()

    def _read(self) -> None:
        try:
            media = _state.probe(self._source, timeout=END_HEAD)
        except Exception as exc:
            self.set_exception(exc)
        else:
            self.set_result(media)


def _end_ahead(source: str) -> _Ahead:
    """Паспорт ``source``: с полки, если хвост уже узнан, иначе голова и хвост заново.

    Отбор раздачи в CLI хвост не читает вовсе, и куски конца файла служба раздач качает
    только здесь, уже после первого кадра.
    """
    return _Ahead(source)
