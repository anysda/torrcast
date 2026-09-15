"""Сколько секунд странице ещё дозапрашивать обложки готового списка.

Потолок :data:`~hass.search_job.POSTERS_BY` идёт от начала захода, а заход бывает старше
вкладки: вкладка, открытая через минуту после прошлой, застаёт тот же заход. Считай она
потолок от своего начала, её опрос приходил за потолком сервера, заставал заход старым и
гнал новый круг поиска по индексерам.
"""

from __future__ import annotations

import hass.search_progress as progress


def posters_left(query: str) -> float:
    """Остаток потолка у захода этого запроса; нет захода - ноль."""
    with progress._jobs_lock:
        job = progress._jobs.get(query.strip().casefold())
    return 0.0 if job is None else job.posters_left()


__all__ = ["posters_left"]
