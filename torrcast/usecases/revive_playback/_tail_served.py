"""Отдан ли приёмнику хвост картины: от места показа до последнего кадра куски лежат подряд.

Спрашивают его ступень подъёма (:func:`torrcast.usecases.revive_playback._resurrect._resurrect`)
и обрыв на хвосте (:func:`torrcast.usecases.revive_playback._tail_cut._tail_cut`).
"""

from __future__ import annotations

from typing import Final

from torrcast.usecases.feed_pack.feed import Feed

#: Допуск на дробную арифметику сетки: конец последнего куска и длительность - одно число.
SERVED_SLACK: Final = 0.5


def _tail_served(feed: Feed, pos: float) -> bool:
    """Правда ли показу от ``pos`` до конца картины есть что отдать без единой дыры.

    🔴 Погасший или замерший у самого конца приёмник - это титры, только когда хвост
    упакован и лежит перед ним. Иначе это наш обрыв: стенд, «Отчаянные домохозяйки» s3e2,
    упаковка встала на куске 258 из 270, приёмник стоял на 2579.5 из 2702.7, потом ошибка -
    и доля 95 % засчитала серию досмотренной, хотя последних двух минут никто не видел.
    """
    return feed.duration > 0 and feed.front(pos) >= feed.duration - SERVED_SLACK
