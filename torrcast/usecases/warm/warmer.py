"""Фоновый прогрев всего фильма на диск.

Поднимает его показ (:mod:`torrcast.usecases.playback`), спрашивают статус и журнал.
"""

from __future__ import annotations

from dataclasses import dataclass

import torrcast.usecases.warm._state as _state
from torrcast.usecases.warm.chain import _ask_follow, _chain, _nap
from torrcast.usecases.warm.forecast import _forecast
from torrcast.usecases.warm.lay_heavy import _lay_heavy
from torrcast.usecases.warm.line import _line
from torrcast.usecases.warm.missing import _missing, _pending
from torrcast.usecases.warm.run import _run
from torrcast.usecases.warm.stall import _stall, _trace
from torrcast.usecases.warm.throttle import _Frozen, _may_resume, _resume, _throttle
from torrcast.usecases.warm.verify import _inspect, _verify
from torrcast.usecases.warm.wait_for_picture import _wait_for_picture
from torrcast.usecases.warm.warmer_state import _State


@dataclass(slots=True)
class Warmer(_State):
    """Фоновый прогрев всего фильма на диск (:class:`Vault`).

    Порядок работы: сначала вперёд от места, откуда начали смотреть, — это то, что
    понадобится раньше всего, — потом голова фильма, если начали с середины. Внутри
    каждого куска работы это ОДИН прогон ffmpeg от края до края (см. заголовок модуля).
    """

    def line(self) -> str:
        """Строка о прогреве для журнала и статуса (:func:`_line`)."""
        return _line(self)

    # ------------------------------------------------------------------ внутреннее

    def _pending(self) -> bool:
        """Осталась ли прогреву работа (:func:`_pending`)."""
        return _pending(self)

    def _missing(self) -> tuple[int, int] | None:
        """Куда идти прогреву (:func:`_missing`)."""
        return _missing(self)

    def _wait_for_picture(self) -> None:
        """Дождаться запаса живого показа (:func:`_wait_for_picture`)."""
        _wait_for_picture(self)

    def _work(self) -> None:
        """Нитка прогрева: крутится, пока идёт показ, участок за участком."""
        self._wait_for_picture()
        # ``trouble`` тут не для порядка: им кончается и упёртый бюджет, и место, которое
        # так и не легло на сетку (:meth:`_verify`). Без этого условия прогрев ходил бы
        # кругами по одному и тому же непрогретому куску.
        while not self.stopped and not self.trouble:
            try:
                if self._must_yield():
                    # Уступать надо не только НАЧАТЫМ прогоном, но и не начатым. Между
                    # решением «пора греть» и первым :meth:`_throttle` прогрев успевает
                    # поднять пробный прогон (:meth:`_run`) - ещё один ffmpeg и ещё один
                    # запрос в ту же раздачу, и он не заморожен ничем. Разбор живого
                    # показа: пробный прогон встал ровно внутрь чужого захода на 15-й
                    # секунде, а сам прогрев замер через миллисекунду после старта - то
                    # есть весь процессор, который прогрев в ту минуту отобрал, был
                    # процессором пробного прогона.
                    _state._environment.sleep(0.5)
                    continue
                job = self._missing()
                if job is None:
                    left = self._spots_left()
                    if left:
                        # Фильм лёг копией целиком - осталось привести тяжёлые места к
                        # тому же виду, в котором их отдаёт живой показ.
                        self._run(left[0], left[0], spot=True)
                        continue
                    if not self.trouble:
                        if self.done:
                            self._say(self.line())
                            _state._environment.mark("прогрев готов", секунд=round(self.warmed))
                            self._trace("ready")
                        else:
                            # Лежит всё, что прогрев в силах положить, но часть мест -
                            # копиями тяжелее потолка приёмника, а перекодировать их нечем
                            # (перекод выключен или профиль тяжести их промахнул). «Готово»
                            # это назвать нельзя - под этими местами показу нужна сеть, -
                            # а вот работа прогрева кончилась, и цепочка идёт дальше.
                            self._stall(
                                "места тяжелее потолка приёмника остались копией - "
                                "без сети их не досмотреть"
                            )
                        self._chain()
                    return
                tight = self.vault.fit(int(self._forecast(job[0], job[0])))
                if tight:
                    self._stall(tight)
                    return
                self._run(*job)
            except Exception as exc:  # прогрев не имеет права ронять показ
                self._say(f"прогрев сорвался ({exc}) - показ идёт как обычно")
                _state._environment.sleep(5.0)

    def _chain(self) -> None:
        """Взяться за следующую серию (:func:`_chain`)."""
        _chain(self)

    def _ask_follow(self) -> _State | None:
        """Собрать прогрев следующей серии (:func:`_ask_follow`)."""
        return _ask_follow(self)

    def _nap(self, seconds: float) -> None:
        """Поспать, просыпаясь на снятие показа (:func:`_nap`)."""
        _nap(self, seconds)

    def _forecast(self, first: int, last: int) -> float:
        """Во сколько байт обойдётся участок (:func:`_forecast`)."""
        return _forecast(self, first, last)

    def _stall(self, why: str) -> None:
        """Прогрев дальше не идёт (:func:`_stall`)."""
        _stall(self, why)

    def _trace(self, event: str, why: str = "") -> None:
        """Доля прогретого в недельный след (:func:`_trace`)."""
        _trace(self, event, why)

    def _run(self, first: int, last: int, spot: bool = False) -> None:
        """Один прогон ffmpeg прогрева (:func:`_run`)."""
        _run(self, first, last, spot)

    def _lay_heavy(self, slot: int, size: int) -> bool:
        """Уложить кусок тяжелее потолка приёмника (:func:`_lay_heavy`)."""
        return _lay_heavy(self, slot, size)

    def _inspect(self, done: int, edge: int) -> int:
        """Сверить с сеткой всё, что легло (:func:`_inspect`)."""
        return _inspect(self, done, edge)

    def _verify(self, slot: int) -> str:
        """Приговор уложенному куску (:func:`_verify`)."""
        return _verify(self, slot)

    def _throttle(self, packer: _Frozen) -> None:
        """Замереть, пока показ просит процессор (:func:`_throttle`)."""
        _throttle(self, packer)

    def _may_resume(self) -> bool:
        """Пора ли оживлять замерший прогрев (:func:`_may_resume`)."""
        return _may_resume(self)

    def _resume(self, packer: _Frozen) -> None:
        """Снять паузу с замершего прогона (:func:`_resume`)."""
        _resume(self, packer)
