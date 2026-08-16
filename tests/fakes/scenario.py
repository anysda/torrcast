"""Запоминает запросы сценария и возвращает заранее заданный ответ."""

from dataclasses import dataclass, field
from typing import Generic, TypeVar

Request = TypeVar("Request")
Result = TypeVar("Result")


@dataclass
class FakeScenario(Generic[Request, Result]):
    result: Result
    requests: list[Request] = field(default_factory=list)

    def __call__(self, request: Request) -> Result:
        self.requests.append(request)
        return self.result
