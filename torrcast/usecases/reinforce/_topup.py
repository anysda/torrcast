"""Долив опоздавшего индексера в пул уже выбранной картины; зовёт сценарий показа."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.profile import Profile
from torrcast.usecases.reinforce._foreign_note import _foreign_note
from torrcast.usecases.reinforce.configure import _catalogue_port
from torrcast.usecases.reinforce.plan_for import plan_for

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.config import Config
    from torrcast.ports.progress.progress import Progress
    from torrcast.usecases.select.plan import Plan


def _topup(
    plan: Plan,
    args: Args,
    config: Config,
    profile: Profile,
    progress: Progress,
    menu: frozenset[str] = frozenset(),
) -> Plan:
    """Долить опоздавший индексер в пул УЖЕ выбранной картины (TC-118).

    🔴 Круг индексеров уходит по кворуму (:data:`~torrcast.domain.quorum_indexer.QUORUM_INDEXERS`),
    и опоздавший доезжает, когда список картин человек уже прочитал. Место вызова выбрано
    ровно по одному правилу: **менять то, на что человек смотрит, нельзя**. Поэтому
    долив зовётся ПОСЛЕ ответа на меню, и права у него ровно одно - пополнить пул той
    картины, которую и выбрали:

    * список картин, их порядок и дефолт долив не трогает вовсе - меню уже напечатано,
      и подменить в нём номер или первую живую часть значило бы соврать задним числом;
    * картина, которой в меню не было, из долива в него не попадает - её и предложить
      уже некому. Но и молча она не пропадает (TC-238): её называет одна честная
      строка (:func:`_foreign_note`), как и всякое авто-решение;
    * а вот верх ОТБОРА долив поменять вправе - выбирали картину, а не раздачу, - но
      молча этого не делает: строка ниже называет и опоздавшего, и то, что верх другой.

    Пул при этом только растёт: старые раздачи остаются теми же объектами, и прогрев,
    пущенный под меню, переезжает на новые номера (:meth:`Bench.reorder`), а не
    выбрасывается. Долив пустой или ничего не добавил - план возвращается прежним.
    """
    from torrcast.domain.cluster import cluster

    rows = plan.late()
    if not rows:
        return plan
    extra = _catalogue_port().to_releases(rows)
    have = {r.magnet for r in plan.picture.releases}
    # Кластер тут - судья принадлежности, а не сборщик: спрашиваем у него, какие из
    # приехавших раздач относятся к ТОЙ ЖЕ картине, и берём только их. Сам пул собираем
    # заменой поля, чтобы прежние релизы остались прежними объектами - по ним прогрев и
    # ищет своё новое место.
    grown = next(
        (p for p in cluster([*plan.picture.releases, *extra]) if p.key == plan.picture.key), None
    )
    mine = {r.magnet for r in grown.releases} if grown is not None else set()
    add = [r for r in extra if r.magnet in mine and r.magnet not in have]
    # Чужая картина (TC-238): в меню её внести нельзя, но и пропасть молча она не
    # должна - строка печатается независимо от того, был ли долив в свою картину.
    _foreign_note([r for r in extra if r.magnet not in mine], menu, progress)
    if not add:
        return plan
    fresh = plan_for(
        replace(plan.picture, releases=[*plan.picture.releases, *add]),
        args,
        config,
        profile,
        # Знаменатель битрейта переживает долив: замер паспорта или хронометраж справки
        # не превращается обратно в прикидку от того, что доехал опоздавший индексер.
        # Прикидка же и остаётся прикидкой - своё число ей назовут справка или паспорт.
        runtime=plan.runtime if not plan.runtime_estimated else 0.0,
        studio=plan.studio,
    )
    if not fresh.ranked:  # отнимать уже показанное долив не вправе
        return plan
    fresh.kin = plan.kin
    named = ", ".join(sorted({r.indexer for r in add if r.indexer}))
    who = named or phrase("reinforce.late_indexer")
    changed = bool(plan.ranked) and fresh.ranked[0].magnet != plan.ranked[0].magnet
    counts = phrase(
        "reinforce.topup_counts", now=len(fresh.picture.releases), was=len(plan.picture.releases)
    )
    tail = phrase("reinforce.topup_changed") if changed else ""
    progress.note(phrase("reinforce.arrived_after_list", who=who) + counts + tail)
    return fresh
