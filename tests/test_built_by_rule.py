"""Проверяет клеймо правила отбора: тело чужой сборки своим не считается."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from web.built_by_rule import FIELD, RULE, built_by_rule


def test_a_body_stamped_with_the_current_rule_is_ours() -> None:
    """Клеймо на месте и оно нынешнее - тело годится и показывать, и хранить."""
    body: dict[str, JsonValue] = {FIELD: RULE, "fresh": [], "popular": [], "built_at": None}

    assert built_by_rule(body)


def test_a_body_from_another_rule_is_not_ours() -> None:
    """Сборка прежним правилом негодна: в ней плитки, которых нынешний отбор не пустил бы."""
    assert not built_by_rule({FIELD: RULE - 1, "fresh": [], "popular": []})


def test_a_body_without_the_stamp_is_not_ours() -> None:
    """Тело без клейма - с диска прежней версии, правила своего оно не называет."""
    assert not built_by_rule({"fresh": [], "popular": [], "built_at": None})
