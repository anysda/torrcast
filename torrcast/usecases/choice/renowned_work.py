"""Namesakes that are versions of the best-known work the offline map proves among them."""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.proof_in_map import proof_in_map
from torrcast.domain.slugify import slugify

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def renowned_work(plans: list[Plan], numbers: list[int]) -> list[int]:
    """Numbers of the namesakes of the best-known proven work; all of them when none is proven.

    A swarm says how lively a release is, not which picture a bare name means: «Блеф» of
    2026 and of 1976 are different works, and «Сталкер» 1979 must not yield to a thriller
    whose dub borrowed the name. A work is the map's original title: a remake keeps it
    («Как приручить дракона» 2010 and 2025), so among its versions the liveliest is still
    taken (TC-812). A namesake the map does not prove gives way to one it does.
    """
    proofs = {n: proof_in_map(plans[n - 1].picture, _search_state._search_known) for n in numbers}
    proven = {n: proof for n, proof in proofs.items() if proof is not None}
    if not proven:
        return numbers
    work = _work(max(proven.values(), key=lambda proof: proof.votes))
    return [n for n in numbers if n in proven and _work(proven[n]) == work]


def _work(proof: MapPicture) -> str:
    return slugify(proof.original or proof.name)


__all__ = ["renowned_work"]
