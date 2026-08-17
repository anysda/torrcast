"""Обход адресов: параллельность тут не оптимизация, а условие пригодности."""

from __future__ import annotations

import pytest

from torrcast.adapters.chromecast import scan
from torrcast.adapters.chromecast.scan.by_scan import BUDGET, WORKERS, by_scan


def test_only_the_addresses_that_answered_come_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Обход возвращает адреса живых приёмников и сохраняет их порядок.

    Порядок держит сортировку меню предсказуемой: пункт «второй телевизор» не должен
    прыгать между запусками из-за того, кто ответил быстрее.
    """
    monkeypatch.setattr(scan, "alive", lambda address, timeout=0.0: address.endswith(("50", "60")))

    assert by_scan(["10.0.0.9", "10.0.0.50", "10.0.0.60"]) == ["10.0.0.50", "10.0.0.60"]


def test_an_empty_list_does_not_raise_a_pool_at_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """Обходить нечего - и поток заводить незачем: пустой пул ThreadPoolExecutor запрещает."""
    monkeypatch.setattr(scan, "alive", lambda address, timeout=0.0: True)

    assert by_scan([]) == []


def test_the_budget_stops_the_walk_even_if_the_subnets_are_many(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Бюджет - второй предохранитель: лучше показать найденное, чем ждать дольше.

    Нулевой бюджет означает «время уже вышло», и ни один адрес щупаться не должен.
    """
    asked: list[str] = []

    def probe(address: str, timeout: float = 0.0) -> bool:
        asked.append(address)
        return True

    monkeypatch.setattr(scan, "alive", probe)

    assert by_scan(["10.0.0.1", "10.0.0.2"], budget=-1.0) == []
    assert asked == []


def test_the_walk_is_wide_enough_for_a_home_subnet_and_bounded_in_time() -> None:
    """128 адресов разом и 25 секунд на всё: последовательный обход ``/24`` - четыре минуты.

    Упирается это не в процессор, а в сокеты и таймауты, поэтому ширина такая большая.
    """
    assert WORKERS == 128
    assert BUDGET == 25.0
