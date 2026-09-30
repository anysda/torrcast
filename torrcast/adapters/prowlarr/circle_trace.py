"""Кладёт расклад круга индексеров в недельный след и в секундомер старта."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from torrcast.adapters.filesystem.stopwatch.mark import mark
from torrcast.adapters.filesystem.trace_journal.emit import emit


def circle_trace(
    *,
    got: Mapping[str, int],
    silent: Sequence[str],
    banned: Sequence[str],
    ms: Mapping[str, int],
    fallback: bool,
    late: Sequence[str],
    budgets: Mapping[str, float],
    cut: Sequence[str] = (),
    names: bool = False,
    held_ms: int = 0,
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

    ``names`` - круг имён картины (у него своё ядро), ``held_ms`` - сколько круг держал
    поиск от отправки до ухода с тем, что успело: по этим двум видно, какой круг держал шаг.
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
        cut=list(cut),
        names=names,
        held_ms=held_ms,
    )
    if banned:
        mark("индексеры", заблокированы=list(banned))
    if silent:
        mark("индексеры", молчат=list(silent), бюджет=dict(budgets))


__all__ = ["circle_trace"]
