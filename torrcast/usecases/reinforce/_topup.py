"""Долив опоздавшего индексера в пул уже выбранной картины; зовёт сценарий показа."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from torrcast.domain.profile import Profile
from torrcast.usecases.reinforce._foreign_note import _foreign_note
from torrcast.usecases.reinforce._plan_for import _plan_for
from torrcast.usecases.reinforce.configure import _catalogue_port

if TYPE_CHECKING:
    from torrcast.domain.config import Config
    from torrcast.ports.choice_types import Args, _Plan
    from torrcast.ports.progress import Progress


def _topup(
    plan: _Plan,
    args: Args,
    config: Config,
    profile: Profile,
    progress: Progress,
    menu: frozenset[str] = frozenset(),
) -> _Plan:
    """Долить опоздавший индексер в пул УЖЕ выбранной картины (TC-118).

    🔴 Круг индексеров уходит по кворуму (:data:`~torrcast.domain.quorum_indexer.QUORUM_INDEXERS`), и
    опоздавший доезжает, когда список картин человек уже прочитал. Место вызова выбрано
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
    пущенный под меню, переезжает на новые номера (:meth:`_Bench.reorder`), а не
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
    fresh = _plan_for(
        replace(plan.picture, releases=[*plan.picture.releases, *add]), args, config, profile
    )
    if not fresh.ranked:  # отнимать уже показанное долив не вправе
        return plan
    fresh.kin = plan.kin
    who = ", ".join(sorted({r.indexer for r in add if r.indexer})) or "опоздавший индексер"
    changed = bool(plan.ranked) and fresh.ranked[0].magnet != plan.ranked[0].magnet
    progress.note(
        f"«{who}» доехал после списка: раздач {len(fresh.picture.releases)}"
        f" вместо {len(plan.picture.releases)}" + (", верх отбора другой" if changed else "")
    )
    return fresh
