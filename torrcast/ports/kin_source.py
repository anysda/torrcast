"""Спрашивает у Wikidata родню картины по другим частям её франшизы."""

from typing import Protocol

from torrcast.domain.facts.kin import Kin


class KinSource(Protocol):
    """Родня по Q-идентификатору картины; франшизы нет - пустой список, сеть молчит - отказ.

    🔴 Пустой список и молчание сети тут РАЗНЫЕ ответы: первый кэшируется навсегда,
    второй не кэшируется вовсе (:meth:`torrcast.usecases.franchise_kin.FranchiseKin.of`).
    """

    def kin(self, entity: str, timeout: float) -> list[Kin]: ...

    def kin_many(self, entities: list[str], timeout: float) -> dict[str, list[Kin]]: ...
