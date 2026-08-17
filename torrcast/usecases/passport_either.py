"""Паспорт, когда тип картины неизвестен; зовёт сценарий паспорта."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable

from torrcast.domain.facts.origin import Origin, _same_picture_origin
from torrcast.domain.facts.settings import (
    FACTS_BUDGET,
    HTTP_TIMEOUT,
    SOURCE_MAP,
    SOURCE_WIKIDATA,
)
from torrcast.domain.facts.with_source import with_source
from torrcast.domain.facts.without_source import without_source
from torrcast.ports.date_source import DateSource


class PassportEither:
    """Обе статьи разом, а одинокому ответу - второй источник года."""

    def __init__(self, typed: Callable[[str, bool, float], Origin], dates: DateSource) -> None:
        self.typed = typed
        self.dates = dates

    def of(self, title: str, budget: float = FACTS_BUDGET) -> Origin:
        """Паспорт, когда тип картины неизвестен: пробуем и фильм, и сериал, верим согласию.

        Тип статьи в Википедии разводит фильм и сериал по разным статьям, и спека требует его
        подсказывать. На пустой русской выдаче взять его неоткуда, а подсказать наугад -
        открыть дыру: с ``series=True`` «Восхождение» уводит в чужой сериал «Hunyadi» 2024
        вместо фильма Шепитько, а с ``series=False`` «Дедвуд» даёт фильм 2006 вместо сериала
        2004. Поэтому спрашиваем обе статьи разом и берём ответ, только если фильм и сериал
        сошлись на одной картине (один оригинал или один год). Разошлись - честнее промолчать:
        пустой паспорт гейт добора переживёт, а чужая статья открыла бы подмену.

        ⚠️ Ответил ровно один путь - паспорт отдаётся БЕЗ ГОДА, и это главная тонкость. Такой
        ответ никем не подтверждён: второй путь молчит не потому, что картины другого типа
        нет, а потому, что статьи о ней нет в русской Википедии. «Атака титанов» - ровно этот
        случай: статьи об аниме-сериале нет вовсе, отвечает только фильм, и он приносит верное
        имя ``Attack on Titan`` вместе с ЧУЖИМ годом 2015 (у сериала 2013). Имя и год стоят
        разного: именем добор ищет раздачи, и худшее, чем оно грозит, - лишние или пустые
        раздачи; а год объявлен сильнее выдачи, и на нём стоят гейты, которые молча выкидывают
        «не ту» картину - с годом 2015 из каталога вылетает весь сериал 2013 года. Поэтому
        одинокому ответу верим ровно настолько, насколько это безопасно: имя берём, год - нет.

        Живая проба по 30 именам: путь остаётся один у 10 из них, год при этом теряют шестеро
        («Моана» 2016, «Во все тяжкие» 2008, «Ход королевы» 2020, «Иван Васильевич меняет
        профессию» 1973, «Семнадцать мгновений весны» 1973 - верные, «Атака титанов» 2015 -
        чужой). Пять верных гейтов за одну молчаливую подмену - размен в ту сторону, которую
        требует спека, и справка при этом не замолкает: имя латиницей остаётся у всех шестерых.

        ⚠️ TC-243. ``budget`` тут СРОК, а не мерка на каждый шаг. Два пути идут разом и в срок
        укладываются оба, но следом за одиноким ответом шёл второй источник
        (:meth:`_second_source_year`) - со своим полным бюджетом сверх уже потраченного, то
        есть режим «оба типа» стоил вдвое дороже обещанного. Пока потолок был полторы секунды,
        лишняя терялась в шуме; на пустой выдаче, где справке отдают весь остаток цели, эти
        «вдвое» - вся цель до картинки. Считаем от срока: сколько осталось, столько и спрашиваем.
        """
        deadline = time.monotonic() + budget
        box: dict[bool, Origin] = {}

        def look(series: bool) -> None:
            box[series] = self.typed(title, series, budget)

        threads = [threading.Thread(target=look, args=(s,), daemon=True) for s in (False, True)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        movie, show = box.get(False, Origin()), box.get(True, Origin())
        if movie and show:
            return movie if _same_picture_origin(movie, show) else Origin()
        lone = movie or show
        year = self._second_source_year(lone, max(0.0, deadline - time.monotonic()))
        alone = Origin(
            title=lone.title,
            year=year,
            name=lone.name,
            entity=lone.entity,
            guessed=lone.guessed,
            source=lone.source,
        )
        if year is None:
            # Поверх статьи карта даёт ровно одно - год (:meth:`Passport._typed`). Одинокий
            # ответ год теряет, и вместе с ним теряется весь вклад карты: оставить её в
            # отметке значило бы записать ей заслугу, которой в отданном паспорте нет.
            return without_source(alone, SOURCE_MAP)
        # Год тут не просто взят у статьи, а подтверждён вторым источником: это его и надо
        # называть, иначе по прогону не отличить подтверждённый год от одинокого.
        return with_source(alone, SOURCE_WIKIDATA)

    def _second_source_year(self, lone: Origin, budget: float) -> int | None:
        """Год одинокого ответа - только если его подтверждает ВТОРОЙ источник (Wikidata P577).

        🔴 TC-134. Одинокий ответ (:meth:`of`) никем не подтверждён: второй путь молчит не
        потому, что картины другого типа нет, а потому, что статьи о ней нет в русской
        Википедии. Прежде год у такого ответа отбирался ВСЕГДА - и это отбирало год у верных
        одиночек тоже («Психо» 1960, «Моана» 2016, «Во все тяжкие» 2008), а на них стоит
        год-опора гейтов добора. Отобрать год у всех - лекарство хуже болезни.

        Второй источник - дата первой публикации P577 из Wikidata, тем же SPARQL и тем же
        IPv4-клиентом, что уже носят хронометраж. Совпал её год с годом статьи - год
        подтверждён двумя источниками, отдаём. Разошлись, второго года нет или Wikidata
        молчит - МОЛЧИМ: год роняем, а не выбираем «поудачнее». При расхождении источников
        чужой год страшнее пустого - им гейт добора молча выкидывает всю картину.

        Хоп стоит времени до меню, поэтому спрашиваем P577 ТОЛЬКО когда год реально нужен: у
        ответа он есть (иначе сверять нечего) и есть чем спросить второй источник (``entity``).
        Латинописанное аниме приходит без Q-идентификатора - тогда второго источника нет, и
        год остаётся неподтверждённым, ровно как раньше.
        """
        if lone.year is None or not lone.entity:
            return None
        return lone.year if self.confirmed_year(lone.entity, lone.year, budget) else None

    def confirmed_year(self, entity: str, year: int, budget: float = FACTS_BUDGET) -> bool:
        """Подтверждает ли Wikidata (P577) год статьи. Молчание/расхождение/ошибка - ``False``.

        Год живёт в бюджете справки, а лишний хоп его тратит, поэтому запрос идёт в отдельном
        потоке с ``join`` по бюджету: залипший сокет держит демона, а не путь до меню. Любая
        ошибка (сети нет, v6 висит в SYN-SENT, Wikidata ответила не так) - тоже ``False``:
        неподтверждённый год честнее чужого.
        """
        box: list[int | None] = []

        def work() -> None:
            with contextlib.suppress(Exception):
                box.append(self.dates.published(entity, min(HTTP_TIMEOUT, budget)))

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        thread.join(budget)
        return bool(box) and box[0] == year
