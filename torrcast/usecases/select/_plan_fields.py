"""Поля плана показа: пул релизов картины, её серия и пороги, которыми судят вес.

Наследует их :class:`torrcast.usecases.select.plan.Plan`, и только он.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.domain._series import _Series
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.domain.release import Release
from torrcast.usecases.select._nobody_waiting import _nobody_waiting
from torrcast.usecases.select._nothing_late import _nothing_late


@dataclass(slots=True)
class _PlanFields:
    """Из чего состоит план: пул релизов картины, её серия и пороги веса."""

    picture: Picture
    ranked: list[Release]
    runtime: float
    #: Потолок ОТБРАКОВКИ, Мбит/с: выше него релиз не берём вовсе (см. :func:`plan_for`).
    warn_mbit: float
    series: _Series | None = None
    #: Порог ПЕРЕКОДИРОВАНИЯ, Мбит/с: выше него куски перекодируются, а релиз годен.
    #: Ноль - перекодирование выключено, и тогда отбраковка и порог это одно число.
    recode_at: float = 0.0
    #: Потолок для тех, кого сплошной перекод не спасает, Мбит/с: выше него релиз годен
    #: только при перекоде ЦЕЛИКОМ и только пока кадр не выше 1080p
    #: (:attr:`torrcast.domain.config.Config.bitrate_hard_mbit`). Ноль - ступени нет.
    hard_mbit: float = 0.0
    #: Ворота отбора открыты: живых именных кандидатов у картины нет (:func:`gate_open`),
    #: и молчаливые имена идут в очередь наравне с именными.
    loose: bool = False
    #: Ворота последней надежды открыты: живого кандидата с нужной серией нет ВООБЩЕ
    #: (:func:`last_hope`), и в очередь пускается названный HEVC — играть его будет
    #: сплошной перекод. Перекодирование выключено — ворота закрыты всегда.
    last_resort: bool = False
    #: HEVC объявлен своим ресивером как играющий копией через наш HLS.
    copy_hevc: bool = False
    #: Другие части той же франшизы, до меню не доехавшие: их нет в списке картин, но в
    #: выдаче они есть и раздачи у них живые. Нужны одной строке отказа (:func:`kin_line`).
    kin: list[Picture] = field(default_factory=list)
    #: Запрос назвал СЕРИЮ (``s1e1``), а не просто имя. Тогда тип сказан вслух, и дефолт
    #: обязан считаться среди сериалов (:func:`asked_kind`), а не среди тёзок-полнометражек.
    asked_series: bool = False
    #: :attr:`runtime` — настоящая длительность из справки, а не прикидка (:func:`_timed`).
    runtime_known: bool = False
    #: Раздачи картины, не доехавшие даже до :attr:`ranked`: нужного сезона в них нет по
    #: их же именам. Нужны счёту отсева (:func:`queue_drops`), чтобы он сходился с пулом.
    off_season: int = 0
    #: Выдача опоздавших индексеров: круг ушёл по кворуму, а эти доехали позже (TC-118).
    #: Зовётся ОДИН раз и только после ответа на меню - :func:`_topup`.
    late: Callable[[], list[RawResult]] = _nothing_late
    #: 🔴 TC-703. Кто из индексеров ещё в пути: их части каталога в пуле нет. Признак
    #: неполноты выдачи, и отказ по пустой очереди обязан его назвать (:func:`unfit_line`)
    #: - иначе «раздачи её негодны» звучит приговором картине, а спрошен был не весь
    #: каталог. Спрашивается ПОСЛЕ долива: доехавший из этого счёта уже ушёл.
    waiting: Callable[[], tuple[str, ...]] = _nobody_waiting
