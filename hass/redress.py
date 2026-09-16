"""Дозапрос обложек готового списка захода, когда тишина источника кончилась.

Его заводит опрос (:func:`hass.search_progress.search_progress`), застав картинки в пути
после финала. Имена только прибавляются, а список, который за это время сменил
досчитанный круг, не трогается: у него свой приговор.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from torrcast.domain.torrcast_error import TorrcastError

if TYPE_CHECKING:
    from hass.search_job import SearchJob
    from hass.searching import Offer


def redress(job: SearchJob, offer: Offer) -> None:
    """Завести дозапрос фоном под флагом приговора: опрос его не ждёт."""
    job.judging = True
    threading.Thread(target=_redress, args=(job, offer), daemon=True, name="redress").start()


def _redress(job: SearchJob, offer: Offer) -> None:
    """Дозапрос в своём потоке; флаг приговора снимается, чем бы он ни кончился.

    🔴 Флаг снимается в ``finally``, а не последней строкой. Он держит не только этот
    дозапрос: пока он поднят, опрос считает обложки захода идущими, второй дозапрос не
    заводится, и заход не сменяется свежим до :data:`~hass.search_job.POSTERS_BY`. Упади
    тут что-то неназванное - ответ короче списка роняет ``zip`` ниже, - и страница целую
    минуту опрашивала бы заход, которому уже никто не принесёт ни одной картинки.
    """
    before = job.results
    try:
        try:
            judged = offer(before)
        except (TorrcastError, OSError):
            judged = before
        merged = [
            after if isinstance(after, dict) and after.get("poster") else was
            for was, after in zip(before, judged, strict=True)
        ]
        with job._lock:
            if job.results is before:
                job.results = merged
    finally:
        job.judging = False


__all__ = ["redress"]
