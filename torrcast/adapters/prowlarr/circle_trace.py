"""Кладёт расклад круга индексеров в недельный след и в секундомер старта."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from torrcast.adapters.filesystem.stopwatch import mark
from torrcast.adapters.filesystem.trace_journal import emit


def circle_trace(
    *,
    got: Mapping[str, int],
    silent: Sequence[str],
    banned: Sequence[str],
    ms: Mapping[str, int],
    fallback: bool,
    late: Sequence[str],
    budgets: Mapping[str, float],
) -> None:
    """Записать круг целиком: кто сколько отдал, кто смолчал, кто ещё в пути.

    Поле ``ms`` - НАШ секундомер на месте вызова, а не ``elapsedTime`` истории Prowlarr:
    та не считает провалившиеся и повторные попытки. Метки секундомера заводятся только
    на потерю (это фаза старта), а следу нужен весь круг - отсюда две записи, а не одна.

    Заблокированные названы отдельной строкой от молчунов: молчун не ответил нам, а
    заблокированного мы и не спрашивали - Prowlarr не дал. Смешать их значит спрятать
    причину, по которой каталог урезан, за словом «молчит». Бюджет у каждого свой
    (TC-226), поэтому в фазе он назван поимённо: иначе «молчит YTS, бюджет 20 с» врало бы
    про то, сколько круг на нём простоял.
    """
    emit(
        "search",
        "indexers",
        got=dict(got),
        silent=list(silent),
        banned=list(banned),
        ms=dict(ms),
        fallback=fallback,
        late=list(late),
    )
    if banned:
        mark("индексеры", заблокированы=list(banned))
    if silent:
        mark("индексеры", молчат=list(silent), бюджет=dict(budgets))


__all__ = ["circle_trace"]
