"""Проверки ступени памяти студии."""

from tests.usecases.rank.releases import rel
from torrcast.usecases.rank.studio_step import studio_step

KITCHEN = "Харли Квинн (Сезон 2) WEB-DL 1080p, Dub (The Kitchen Russia)"
OTHER = "Харли Квинн (Сезон 2) WEB-DL 1080p, MVO (Good People)"


def test_remembered_studio_stands_above_the_rest() -> None:
    assert studio_step(rel(KITCHEN, title="Харли Квинн"), "The Kitchen Russia") == 0
    assert studio_step(rel(OTHER, title="Харли Квинн"), "The Kitchen Russia") == 1


def test_without_memory_the_step_is_flat() -> None:
    kitchen = rel(KITCHEN, title="Харли Квинн")
    other = rel(OTHER, title="Харли Квинн")
    assert studio_step(kitchen) == studio_step(other) == 0


def test_unknown_studio_is_judged_like_a_silent_name() -> None:
    unknown = rel("Харли Квинн (Сезон 2) WEB-DL 1080p, Dub (Studio 42)", title="Харли Квинн")
    assert studio_step(unknown, "The Kitchen Russia") == 1
