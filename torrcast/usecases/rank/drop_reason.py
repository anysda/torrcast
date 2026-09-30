"""Почему раздача не доехала до очереди отбора; зовут счёт отсева и снижение ступени."""

from __future__ import annotations

from typing import Protocol

from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.rank.foreign_reason import foreign_reason
from torrcast.usecases.rank.is_disc import is_disc
from torrcast.usecases.rank.is_extra import is_extra
from torrcast.usecases.rank.off_season import (
    _codec,
    _disc,
    _extras,
    _heavy,
    _hevc,
    _quiet,
    _small,
    _source,
)
from torrcast.usecases.rank.over_ceiling import over_ceiling


class _Judged(Protocol):
    """План в объёме, которым судят одну раздачу: цель сериала и потолки отбора.

    Полный :class:`torrcast.usecases.select.plan.Plan` сюда не приходит: правилу нужны семь
    его полей, и ровно они названы. Тем же объёмом план видят счёт отсева и снижение
    ступени, которые это правило и зовут.
    """

    picture: Picture
    runtime: float
    warn_mbit: float
    hard_mbit: float
    copy_hevc: bool
    last_resort: bool

    @property
    def want(self) -> Episode | None: ...


def drop_reason(release: Release, plan: _Judged) -> str:
    """Почему раздача не доехала до очереди отбора; пусто — доехала.

    🔴 TC-186. Пул картины и очередь отбора — не одно и то же: между ними стоят ворота
    (:func:`is_candidate`), сезонный фильтр и потолок битрейта, и на замере тысячи
    запросов между ними терялось 895 раздач из 3164 — без строки на экране и без
    события в недельном следе. «В журнале нет строки» это не «события не было»:
    отказавшая арифметика выглядела в следе ровно как её отсутствие.

    Причины перечислены в том же порядке, в каком судит :meth:`Plan.candidates`, и
    каждая раздача получает ПЕРВУЮ подошедшую: у выкинутой их бывает несколько сразу,
    а объяснять человеку надо ту, на которой её и выкинули.

    Первой судится чужая раздача (:func:`foreign_reason`): кино другого года, серии нет,
    другая работа франшизы, поздняя форма. Пока этой ступени тут не было, «It Follows»
    2014 года в пуле «Оно» 2017, выкинутая очередью как другая картина, подписывалась
    первой подошедшей причиной ворот - «кодек не тот», хотя кодек у неё годный.
    """
    if foreign := foreign_reason(release, plan.picture, plan.want):
        return foreign
    if is_disc(release):
        return _disc()
    if is_extra(release, plan.runtime):
        return _extras()
    if over_ceiling(release, plan.runtime, plan.warn_mbit, plan.hard_mbit):
        return _heavy()
    if release.is_hevc and plan.copy_hevc:
        return ""
    if release.is_hevc and not (plan.last_resort or plan.copy_hevc):
        return _hevc()
    # Дальше раздача не прошла ворота (:attr:`~torrcast.domain.release.Release.prime`), и причина
    # у ворот ровно та, чем имя о себе сказало: назван чужой кодек, назван мелкий кадр,
    # назван не-HD-источник. Не сказало ничего - это молчание, и оно отдельная причина:
    # молчаливую раздачу судит ffprobe, когда ворота открыты (:attr:`Plan.loose`).
    if release.codec:
        return _codec()
    if release.height:
        return _small()
    if release.source:
        return _source()
    return _quiet()
