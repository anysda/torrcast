"""Проверяет срок доезда обложек: бюджет от старта процесса, но не меньше минимума от вопроса."""

from __future__ import annotations

from web.fill_deadline import FILL_AT_LEAST, FILL_BY, READY_BY, fill_deadline


def test_an_early_ask_waits_until_the_budget_from_the_process_start() -> None:
    """Лента пришла через 4.7 с после старта: срок - ``FILL_BY`` от старта, не от вопроса."""
    assert fill_deadline(104.7, 100.0) == 100.0 + FILL_BY


def test_an_ask_at_the_edge_of_the_budget_still_gets_the_least_wait() -> None:
    """Вопрос за полсекунды до бюджета ждёт ``FILL_AT_LEAST``, а не остаток окна."""
    asked = 100.0 + FILL_BY - 0.5
    assert fill_deadline(asked, 100.0) == asked + FILL_AT_LEAST


def test_a_pass_long_after_the_start_counts_from_its_own_ask() -> None:
    """Холодный заход через час ждёт обложки от своего вопроса."""
    assert fill_deadline(3700.0, 100.0) == 3700.0 + FILL_AT_LEAST


def test_the_wait_never_shrinks_as_the_ask_comes_later() -> None:
    """Правило без ступени: чем позже вопрос, тем срок не раньше, и не меньше минимума."""
    asks = [100.0 + step / 10 for step in range(400)]
    deadlines = [fill_deadline(asked, 100.0) for asked in asks]
    assert deadlines == sorted(deadlines)
    assert all(
        end - asked >= FILL_AT_LEAST - 1e-9 for asked, end in zip(asks, deadlines, strict=True)
    )


def test_the_budget_leaves_the_page_poll_and_the_closing_inside_the_goal() -> None:
    """Бюджет обложек меньше цели 30 с; поздний штатный вопрос (19 с) в цель укладывается."""
    assert FILL_BY < READY_BY
    assert fill_deadline(119.0, 100.0) == 100.0 + FILL_BY
