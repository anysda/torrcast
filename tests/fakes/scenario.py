"""Запоминает запросы сценария и возвращает заранее заданный ответ."""

from dataclasses import dataclass, field


@dataclass
class FakeScenario[Request, Result]:
    result: Result
    requests: list[Request] = field(default_factory=list)

    def __call__(self, request: Request) -> Result:
        self.requests.append(request)
        return self.result
