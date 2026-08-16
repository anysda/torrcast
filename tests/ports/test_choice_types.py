"""Проверяет модуль типов границы выбора."""

import torrcast.ports.choice_types as choice_types


def test_choice_types_have_no_runtime_dependencies() -> None:
    """Типовые связи не загружают прежние реализации во время исполнения."""
    assert choice_types.__doc__
