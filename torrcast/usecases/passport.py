"""Паспорт картины: кэш, статья, офлайн-карта; зовёт его поиск на тощей выдаче."""

from __future__ import annotations

import contextlib
import threading
import time

from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import (
    FACTS_BUDGET,
    HTTP_TIMEOUT,
    SOURCE_MAP,
    SOURCE_WIKI,
)
from torrcast.domain.facts.sourced import sourced
from torrcast.domain.facts.with_source import with_source
from torrcast.ports.article_source import ArticleSource
from torrcast.ports.date_source import DateSource
from torrcast.ports.name_catalogue import NameCatalogue
from torrcast.ports.origin_store import OriginStore
from torrcast.usecases.passport_either import PassportEither


class Passport:
    """Оригинальное название латиницей и год выпуска - независимое мнение для гейта."""

    def __init__(
        self,
        articles: ArticleSource,
        catalogue: NameCatalogue,
        store: OriginStore,
        dates: DateSource,
    ) -> None:
        self.articles = articles
        self.catalogue = catalogue
        self.store = store
        self.either = PassportEither(self._typed_now, dates)

    def of(self, title: str, series: bool | None = False, budget: float = FACTS_BUDGET) -> Origin:
        """Паспорт картины из Википедии. Жёсткий потолок по времени и кэш на диске.

        Зовётся только на тощей выдаче, то есть там, где поиск и так собирается идти на
        второй круг по индексерам (1-3 с). Полторы секунды потолка на его фоне не видны, а
        счастливый путь сюда не заходит вовсе.

        ⚠️ Год выдачи сюда НЕ передаётся, и это принципиально: паспорт нужен гейту как
        независимое мнение. Подсказали бы год - справка послушно нашла бы статью под него, и
        сверять после этого было бы нечего: на «Восхождении» с подсказкой ``2019`` она
        уверенно приносила «Hannibal Rising», а без подсказки честно отвечает «1976».

        Молчание сети стоит ровно ``budget``: запрос живёт в отдельном потоке, и залипший
        сокет держит не поиск, а демона, который умрёт вместе с процессом. Любая ошибка -
        пустой паспорт: справка не вправе ни ронять поиск, ни задерживать его сверх обещанного.

        ``series=None`` - тип картины неизвестен (русская выдача пуста, спросить его неоткуда),
        и это отдельный случай: см. :meth:`PassportEither.of`. У сериала и фильма разные
        статьи, так что тип подсказывать надо, а наугад - нельзя (уводит в чужую статью).
        """
        stored = self.store.read(title, series)
        if stored is not None:
            return stored
        if series is None:
            found = self.either.of(title, budget)
            if found:
                self.store.write(title, series, found)
            return found
        return self._typed(title, series, budget, remember=True)

    def _typed_now(self, title: str, series: bool, budget: float) -> Origin:
        """Типизированная проба без записи в кэш: её зовёт режим «оба типа»."""
        return self._typed(title, series, budget, remember=False)

    def _typed(self, title: str, series: bool, budget: float, *, remember: bool) -> Origin:
        """Паспорт для внутренней типизированной пробы без подмены ключа запроса.

        🔴 TC-493. Год из офлайн-карты ДОГАДКЕ справки не подставляется, и на то две причины.

        Первая - она про правду. Карта отвечает на ТОЧНОЕ имя (:attr:`catalogue` ищет по слагу
        запроса), а догадка (:attr:`Origin.guessed`) означает, что имя, которым спросили,
        статья не носит. Сложить их в один паспорт - значит выдать имя одной картины вместе с
        годом другой, а год объявлен сильнее выдачи: им гейт добора молча выбрасывает всю
        картину. Ровно поэтому разбор описки и сам отвечает без года.

        Вторая - про срок. Разбор карты это 150 тысяч строк и полсекунды на первое обращение,
        а `cast` живёт один запрос, так что платит их каждый показ. Ложилась она поверх уже
        потраченного, и потолок в :data:`FACTS_BUDGET` переставал быть потолком: статью
        находили в срок, а паспорт приезжал позже - режим «оба типа» успевал сдаться и отдать
        пустоту. Дороже всего это стоило именно догадке: имя, написанное не так, как подписана
        статья, ищется дольше всего, и полсекунды сверху отнимали у него ответ целиком. Живой
        замер, по одному заходу на процесс (как в жизни): «эксперименты лейн» - оригинал 0 раз
        из 6 при здоровой сети, «Эксперименты Лэйн» - 6 из 6. Написание имени решало не
        «найдётся ли статья», а «влезет ли ответ вместе с чтением файла».

        Читать карту там, где её слово годится, никто не мешает: пустой паспорт и статья без
        года спрашивают её ровно как спрашивали - только уже не сверх срока
        (:meth:`_catalogued`).
        """
        box: list[Origin] = []
        deadline = time.monotonic() + budget

        def work() -> None:
            with contextlib.suppress(Exception):
                box.append(self.articles.look(title, series, min(HTTP_TIMEOUT, budget)))

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        thread.join(budget)
        # Ответ сетевого пути подписан Википедией, если он сам не сказал иначе: последним шагом
        # статья спрашивает ту же карту, и её ответ подписан :data:`SOURCE_MAP`.
        found = sourced(box[0] if box else Origin(), SOURCE_WIKI)
        # После страницы значений сетевому пути нужен второй запрос, и года у него нет.
        # Офлайн-каталог этот год и даёт. Для коротких имён это решающий признак: один
        # транслит не разводит старую картину и свежую тёзку.
        offline = Origin()
        if not found:
            offline = self.catalogue.look(title, series)  # источник единственный - его и ждём
        elif found.year is None and not found.guessed:
            offline = self._catalogued(title, series, max(0.0, deadline - time.monotonic()))
        offline = sourced(offline, SOURCE_MAP)
        if not found:
            found = offline
        elif found.year is None and offline.year is not None:
            found = with_source(
                Origin(
                    title=found.title or offline.title,
                    year=offline.year,
                    name=found.name or offline.name,
                    entity=found.entity,
                    guessed=found.guessed or offline.guessed,
                    namesake=found.namesake,
                    source=found.source,
                ),
                offline.source,
            )
        if found and remember:
            self.store.write(title, series, found)
        return found

    def _catalogued(self, title: str, series: bool, budget: float) -> Origin:
        """Офлайн-карта в отдельном потоке: ДОПОЛНЕНИЕ к паспорту не выходит за срок.

        🔴 TC-493. Разбор карты - 150 тысяч строк и полсекунды на первое обращение, и лежала
        она поверх уже потраченного: статью находили в срок, а паспорт с её годом приезжал
        после. Пока карта была единственным источником, платить это стоило - её и ждут без
        ограничения (:meth:`_typed`). Но когда паспорт уже есть и речь лишь о том, чтобы
        дописать в него год, за потолок ради этого выходить не за что: год приятен, а
        опоздавший паспорт не нужен никому.

        Файл читается один раз на процесс, так что не уложившийся поток дочитает его сам и
        следующему спросившему карта достанется уже готовой.
        """
        box: list[Origin] = []

        def look() -> None:
            with contextlib.suppress(Exception):
                box.append(self.catalogue.look(title, series))

        thread = threading.Thread(target=look, daemon=True)
        thread.start()
        thread.join(budget)
        return box[0] if box else Origin()
