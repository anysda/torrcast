"""Итог обхода после второго спроса: молчание, ставшее приговором, зовётся приговором."""

from __future__ import annotations


def _retried_verdict(
    queue: list[int],
    judged: dict[int, str],
    judged_before: set[int],
    tried: list[str],
    silents: int,
) -> tuple[list[str], int]:
    """Переписать итог обхода, если второй спрос вынес приговор вместо молчания.

    Повторный полный спрос (:meth:`_Bench._recheck`) может не промолчать, а вынести
    приговор: например, метаданные приехали, но нужной серии в раздаче нет. Тогда итог
    обязан говорить о приговоре, а не обещать, что молчавший рой позже оживёт.
    """
    retried = next(
        (number for number in queue if number in judged and number not in judged_before), None
    )
    if retried is None:
        return tried, silents
    rewritten = [
        f"{retried} - {judged[retried]}" if row.startswith(f"{retried} - ") else row
        for row in tried
    ]
    return rewritten, silents - 1
