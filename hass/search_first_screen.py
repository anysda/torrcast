"""Первый ряд выдачи встаёт вместе с обложками своих плиток, а не раньше них.

Превью отвечало через доли секунды от начала захода, а приговор и байты обложек той же
пачки ложились позже на 0.9-1.1 с: человек видел ряд серых плиток, и обложки въезжали в
него поштучно, за 4-6 перерисовок (стенд, первые попытки холодных картин, 8 из 8). Пока у
плиток первого ответа обложка ещё может лечь, опрос получает пустое превью, и страница
держит тот же скелет, что и до первой находки. Держит не дольше :data:`FIRST_SCREEN_BY` от
начала захода: застрявший источник стоит человеку только этот срок, после него ряд выходит
без того, что не доехало. Однажды показанный ряд больше не придерживается никогда.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final

from hass.hit_ask import _about
from hass.shown_covers import _Covers, shown_covers
from torrcast.domain.json_value import JsonValue

if TYPE_CHECKING:
    from hass.search_job import SearchJob

#: Сколько первый ряд ждёт обложки своих плиток от начала захода, секунды.
FIRST_SCREEN_BY: Final = 1.0
#: Сколько плитка, выросшая после первого показа, ждёт свою обложку от первого появления, с.
GROWN_BY: Final = 2.0


def search_first_screen(
    job: SearchJob, results: list[JsonValue], covers: _Covers
) -> list[JsonValue]:
    """Ряд страницы (:func:`shown_covers`); пусто, пока он первый, обложки в пути, срок не вышел."""
    shown = shown_covers(results, covers)
    young = time.monotonic() - job.started_at < FIRST_SCREEN_BY
    if not job.drawn and shown and young and _coming(job, shown, covers):
        return []
    if job.drawn and not job.done:
        shown = _grown(job, shown, covers)
    job.drawn = job.drawn or bool(shown)
    job.on_screen.update(_key(hit) for hit in shown)
    return shown


def _grown(job: SearchJob, shown: list[JsonValue], covers: _Covers) -> list[JsonValue]:
    """Ряд без плиток, выросших после первого показа и ждущих свою обложку до :data:`GROWN_BY`.

    Страница кладёт обложку в уже стоящую плитку только одной общей пачкой (``home.js``,
    ``_COVERS_BY``), и плитка, вставшая голой после пачки, так и осталась бы строкой. Её
    обложка ложилась через 0.5-1.9 с после появления плитки (стенд 02-10-2026, 9 запросов).
    """
    now = time.monotonic()
    kept = []
    for hit in shown:
        key = _key(hit)
        if key and key not in job.on_screen:
            since = job.appeared.setdefault(key, now)
            if now - since < GROWN_BY and _coming(job, [hit], covers):
                continue
        kept.append(hit)
    return kept


def _key(hit: JsonValue) -> str:
    return str(hit.get("key", "")) if isinstance(hit, dict) else ""


def _coming(job: SearchJob, shown: list[JsonValue], covers: _Covers) -> bool:
    """Чья-то обложка ещё может лечь: приговор идёт или не начат, байты или повтор в пути.

    Приговор готового захода уже в его списке (:meth:`SearchJob.run`), а не в ``posters``:
    без ``done`` ряд захода, кончившегося раньше срока, ждал бы весь срок и с легшими байтами.
    """
    unjudged = not job.done and any(
        isinstance(hit, dict)
        and _about(hit) is not None
        and str(hit.get("key", "")) not in job.posters
        for hit in shown
    )
    return job.judging or unjudged or covers.pending(shown)


__all__ = ["FIRST_SCREEN_BY", "GROWN_BY", "search_first_screen"]
