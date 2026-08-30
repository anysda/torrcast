"""Зеркало команды флага языка: она передаёт выбор сценарию и молчит без флага."""

from __future__ import annotations

from torrcast.cli.language import language
from torrcast.domain.args import Args


def test_the_named_language_goes_to_the_scenario_that_remembers_it() -> None:
    seen: list[str] = []

    def remember(chosen: str) -> int:
        seen.append(chosen)
        return 0

    assert language(Args(query=[], language="ru"), remember) == 0
    assert seen == ["ru"]


def test_without_a_flag_there_is_nothing_to_remember() -> None:
    """Команда зовётся и перед чужой работой: без флага она обязана не трогать настройку."""
    seen: list[str] = []

    def remember(chosen: str) -> int:
        seen.append(chosen)
        return 0

    assert language(Args(query=["мумия"]), remember) == 0
    assert seen == []
