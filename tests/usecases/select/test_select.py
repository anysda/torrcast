"""Проверяет сценарий отбора на фейковой зависимости."""

from tests.fakes.scenario import FakeScenario
from torrcast.usecases.select import Select


def test_select_delegates_request() -> None:
    fake = FakeScenario[int, str]("готово")

    assert Select(fake).run(2) == "готово"
    assert fake.requests == [2]
