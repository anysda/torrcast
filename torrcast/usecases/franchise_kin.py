"""Другие части франшизы картины: паспорт даёт Q-идентификатор, Wikidata - соседей."""

from __future__ import annotations

from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.settings import HTTP_TIMEOUT
from torrcast.ports.kin_source import KinSource
from torrcast.ports.kin_store import KinStore
from torrcast.ports.passport_source import PassportSource


class FranchiseKin:
    """Полка родни картины: пустой список - франшизы нет, паспорт не найден, или сеть молчит.

    Кэш стоит ПЕРЕД походом за родней, а не вокруг паспорта: паспорт картины и так кэширован
    своим хранилищем (:class:`~torrcast.usecases.passport.Passport`), а второй поход за той же
    родней избыточен ровно так же, как повторный поход за годом одной и той же картины.
    """

    def __init__(self, passport: PassportSource, kin: KinSource, store: KinStore) -> None:
        self.passport = passport
        self.kin = kin
        self.store = store

    def of(self, title: str, series: bool = False, timeout: float = HTTP_TIMEOUT) -> list[Kin]:
        """Родня картины по названию: без Q-идентификатора спрашивать Wikidata не о чем."""
        entity = self.passport(title, series).entity
        if not entity:
            return []
        cached = self.store.read_kin(entity)
        if cached is not None:
            return cached
        try:
            found = self.kin.kin(entity, timeout)
        except Exception:
            # 🔴 Молчание сети - НЕ «родни нет», и в кэш ему нельзя: ряд лежит на диске
            # и переживает и показ, и обновление продукта. Полка пуста на этот заход,
            # а следующий спросит заново.
            return []
        self.store.write_kin(entity, found)
        return found
