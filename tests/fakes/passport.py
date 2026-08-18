"""Отвечает тестам паспортом картины и запоминает, о чём справку спрашивали."""

from dataclasses import dataclass, field

from torrcast.domain.facts.origin import Origin


@dataclass
class FakePassport:
    """Справка с подложенными ответами: о чём не сказано, о том она молчит.

    Зовётся так же, как боевая :func:`~torrcast.usecases.passport.Passport.of`, и подаётся сценарию
    поиска параметром ``passport``.
    """

    known: dict[str, Origin] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    def __call__(self, title: str, series: bool | None = False, budget: float = 0.0) -> Origin:
        self.asked.append(title)
        return self.known.get(title, Origin())
