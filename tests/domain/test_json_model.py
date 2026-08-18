"""Зеркало :mod:`torrcast.domain.json_model`: знакомые ключи в поля, чужие - за борт."""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain.json_model import json_model


@dataclass(slots=True)
class _Thing:
    """Модель на два поля - ровно чтобы было что собирать."""

    name: str = ""
    count: int = 0


def test_known_keys_become_fields() -> None:
    """Что модель знает, то и получает - и именно из своего ключа."""
    assert json_model(_Thing, {"name": "Дюна", "count": 2}, _Thing.__dataclass_fields__) == _Thing(
        "Дюна", 2
    )


def test_a_key_from_a_newer_version_does_not_break_the_read() -> None:
    """Файл переживает смену версии: незнакомый ключ теряется, а запись читается.

    Урони сборка такой файл - обновление отбирало бы у человека всё состояние показа.
    """
    made = json_model(
        _Thing, {"name": "Дюна", "ключ_из_будущего": True}, _Thing.__dataclass_fields__
    )

    assert made == _Thing("Дюна", 0)


def test_a_missing_key_leaves_the_default_in_place() -> None:
    """Чего в файле нет, то остаётся умолчанием модели, а не пустотой."""
    assert json_model(_Thing, {}, _Thing.__dataclass_fields__) == _Thing()
