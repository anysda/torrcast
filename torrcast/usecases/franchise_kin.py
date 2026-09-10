"""Другие части франшизы картины: паспорт даёт Q-идентификатор, Wikidata - соседей."""

from __future__ import annotations

from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.settings import HTTP_TIMEOUT, SOURCE_WIKI
from torrcast.ports.kin_source import KinSource
from torrcast.ports.kin_store import KinStore
from torrcast.ports.passport_source import PassportSource


class FranchiseKin:
    """Полка родни картины: пустой список - франшизы нет, ``None`` - сеть молчит.

    Кэш стоит ПЕРЕД походом за родней, а не вокруг паспорта: паспорт картины и так кэширован
    своим хранилищем (:class:`~torrcast.usecases.passport.Passport`), а второй поход за той же
    родней избыточен ровно так же, как повторный поход за годом одной и той же картины.
    """

    def __init__(
        self,
        passport: PassportSource,
        kin: KinSource,
        store: KinStore,
        refresh: PassportSource,
    ) -> None:
        self.passport = passport
        self.kin = kin
        self.store = store
        self.refresh = refresh

    def of(
        self, title: str, series: bool = False, timeout: float = HTTP_TIMEOUT
    ) -> list[Kin] | None:
        """Родня картины по названию: без Q-идентификатора спрашивать Wikidata не о чем.

        ``None`` - сеть промолчала и продукт не узнал НИЧЕГО: это не «родни нет», и
        отвечать им как законченной пустой полкой нельзя - тот, кто спросил, обязан
        переспросить позже (:class:`web.related_lookup.RelatedLookup` так и делает).
        Пустой список - только законченный ответ «Wikidata ответила: родни нет».

        Паспорт без Q-идентификатора, не подписанный Википедией, - деградированный: его
        ответила офлайн-карта в минуту молчания сети, и кэш хранит его бессрочно. Такой
        переспрашивается живьём (:func:`~torrcast.usecases.passport.Passport.fresh`) - иначе
        одна оборванная связь гасила полку на всю жизнь установки ещё ДО похода в Wikidata
        (замер 10-09-2026: «Крепкий орешек» и «Форсаж» лежали в `facts.json` с пустым
        ``entity`` и пустой полкой при живых сериях по четыре и десять картин).

        🔴 Род картины сюда приходит из РАЗБОРА РАЗДАЧ, а не из знания, и статья фильма и
        статья сериала в Википедии разные: назвали род неверно - типизированный паспорт
        молчит, и полка гаснет при живой франшизе. Поэтому промолчавший тип переспрашивается
        режимом «оба типа» (``series=None``,
        :class:`~torrcast.usecases.passport_either.PassportEither`) - тем самым, который
        продукт держит ровно на «тип подсказать нечем». Наугад тип не подставляется: обе
        статьи спрашиваются разом и расходятся молчанием, так что настоящий сериал без
        франшизы остаётся с пустой полкой. Замер 10-09-2026 на стенде `.104`: лучшим
        совпадением на «Чужой» продукт называет `tv:чужой:2021`, статьи о сериале с таким
        именем нет вовсе, и полка стояла пустой при шести частях франшизы у фильма 1979.
        """
        origin = self.passport(title, series)
        entity = origin.entity
        if not entity and SOURCE_WIKI not in origin.source:
            entity = self.refresh(title, series).entity
        if not entity:
            entity = self.passport(title, None).entity
        if not entity:
            return []
        cached = self.store.read_kin(entity)
        if cached is not None:
            return cached
        try:
            found = self.kin.kin(entity, timeout)
        except Exception:
            # 🔴 Молчание сети - НЕ «родни нет», и в кэш ему нельзя: ряд лежит на диске
            # и переживает и показ, и обновление продукта. Полка молчит на этот заход,
            # а следующий спросит заново.
            return None
        self.store.write_kin(entity, found)
        return found
