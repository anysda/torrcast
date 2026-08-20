"""Прогрев просит только недостающее: занятое им уже вычтено из свободного места."""

from torrcast.domain.warm_claim import warm_claim


def test_a_fresh_disk_owes_the_warming_its_whole_budget() -> None:
    """Прогретого нет - резервировать надо весь бюджет: занять его прогрев вправе."""
    assert warm_claim(30_000_000_000, 0) == 30_000_000_000


def test_what_the_warming_already_took_is_never_counted_twice() -> None:
    """🔴 TC-725. Свободное место раздела уже не содержит занятого прогревом."""
    assert warm_claim(30_000_000_000, 15_315_748_102) == 14_684_251_898


def test_a_budget_spent_to_the_end_asks_for_nothing_more() -> None:
    """Прогрев выбрал бюджет: расти ему больше некуда, и запас ему не нужен."""
    assert warm_claim(30_000_000_000, 30_000_000_000) == 0


def test_a_budget_overspent_never_turns_the_reserve_upside_down() -> None:
    """Перебор бюджета (бюджет уменьшили руками) не имеет права ОТДАВАТЬ место кэшу."""
    assert warm_claim(30_000_000_000, 44_000_000_000) == 0
