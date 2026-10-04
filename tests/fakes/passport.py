"""Отвечает тестам паспортом картины и запоминает, о чём справку спрашивали."""

import threading
from dataclasses import dataclass, field

from torrcast.domain.facts.origin import Origin
from torrcast.usecases.discover._passport_ahead import AHEAD_THREAD


@dataclass
class FakePassport:
    """Справка с подложенными ответами: о чём не сказано, о том она молчит.

    Зовётся так же, как боевая :func:`~torrcast.usecases.passport.Passport.of`, и подаётся сценарию
    поиска параметром ``passport``.

    ``asked`` - вопросы, ответа на которые поиск ЖДЁТ. Упреждающий вопрос из фоновой нитки
    (:func:`~torrcast.usecases.discover._passport_ahead._passport_ahead`) поиск не ждёт и
    успевает к сроку не всегда, поэтому он пишется отдельно, в ``ahead``: в общем счёте он
    сделал бы любой подсчёт вопросов гонкой с этой ниткой.
    """

    known: dict[str, Origin] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)
    ahead: list[str] = field(default_factory=list)

    def __call__(self, title: str, series: bool | None = False, budget: float = 0.0) -> Origin:
        early = threading.current_thread().name.startswith(AHEAD_THREAD)
        (self.ahead if early else self.asked).append(title)
        return self.known.get(title, Origin())
