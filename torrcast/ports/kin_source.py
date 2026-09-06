"""Спрашивает у Wikidata родню картины по другим частям её франшизы."""

from typing import Protocol

from torrcast.domain.facts.kin import Kin


class KinSource(Protocol):
    """Родня по Q-идентификатору картины; франшизы нет или сеть молчит - пустой список."""

    def kin(self, entity: str, timeout: float) -> list[Kin]: ...
