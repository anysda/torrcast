"""Справка о картинах: договор снят с настоящего вызова пересборки плана."""

from torrcast.domain.facts.fact import Fact
from torrcast.ports.choice_environment import ChoiceFacts


class _Facts:
    def get(self, title: str, year: int | None) -> Fact:
        return Fact(runtime="2 ч 49 мин") if title == "Интерстеллар" else Fact()


def test_a_silent_lookup_answers_with_an_empty_fact_and_not_with_none() -> None:
    """«Не знаю» тут решение, а не отказ: план остаётся на прикидке, и это видно в следе."""
    facts: ChoiceFacts = _Facts()

    assert facts.get("Интерстеллар", 2014).runtime == "2 ч 49 мин"
    assert facts.get("Картины нет нигде", None).runtime == ""
