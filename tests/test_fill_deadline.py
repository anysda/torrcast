"""Проверяет срок доезда обложек: первый холодный заход считает его от старта фона."""

from __future__ import annotations

from web.fill_deadline import FILL_BY, fill_deadline


def test_the_first_pass_counts_from_the_start_not_from_a_late_ask() -> None:
    """Лента пришла через 4.7 с после старта: срок - ``FILL_BY`` от старта."""
    assert fill_deadline(104.7, 100.0) == 100.0 + FILL_BY


def test_a_pass_long_after_the_start_counts_from_its_own_ask() -> None:
    """Холодный заход через час ждёт обложки полный срок от своего вопроса."""
    assert fill_deadline(3700.0, 100.0) == 3700.0 + FILL_BY


def test_an_ask_at_the_edge_of_the_start_window_gets_the_full_wait() -> None:
    """Вопрос ровно на ``FILL_BY`` после старта уже не первый: ждёт полный срок."""
    assert fill_deadline(100.0 + FILL_BY, 100.0) == 100.0 + 2 * FILL_BY
