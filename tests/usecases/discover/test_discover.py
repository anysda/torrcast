"""Проверяет сценарий поиска на фейковой зависимости."""

from tests.fakes.scenario import FakeScenario
from torrcast.usecases.discover.discover import Discover


def test_discover_delegates_request() -> None:
    fake = FakeScenario[str, list[str]](["Матрица"])

    assert Discover(fake).run("матрица") == ["Матрица"]
    assert fake.requests == ["матрица"]
