"""Синхронный поход в Википедию за паспортом картины; зовёт сценарий паспорта."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Sequence

from torrcast.adapters.wiki.closed_wave import closed_wave
from torrcast.adapters.wiki.endpoints import WIKI_HOST, WIKI_PATH
from torrcast.adapters.wiki.wiki_spelling import WikiSpelling
from torrcast.domain.facts.extract_params import extract_params
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.own_name_first import _own_name_first
from torrcast.domain.facts.read_origin import read_origin
from torrcast.domain.facts.redirected_name import redirected_name
from torrcast.domain.facts.search_params import search_params
from torrcast.domain.facts.settings import HTTP_TIMEOUT
from torrcast.domain.facts.titles_for import titles_for
from torrcast.domain.facts.wiki_pages import wiki_pages
from torrcast.domain.facts.wiki_ranked import wiki_ranked
from torrcast.domain.facts.wiki_reply import _article
from torrcast.domain.json_value import JsonValue
from torrcast.ports.json_client import JsonClient
from torrcast.ports.name_catalogue import NameCatalogue


class WikiArticles:
    """Выборка по имени, поиск и разбор описки, а последним словом - офлайн-карта."""

    def __init__(
        self, client: JsonClient, spelling: WikiSpelling, catalogue: NameCatalogue
    ) -> None:
        self.client = client
        self.spelling = spelling
        self.catalogue = catalogue

    def look(self, title: str, series: bool = False, timeout: float = HTTP_TIMEOUT) -> Origin:
        """Синхронный поход за паспортом. Неудача — исключение, его ловит сценарий паспорта.

        Два шага, и второй — только если первый промахнулся. Прямая выборка по именам
        (:func:`titles_for`) дешевле и точнее, ею и закрывается большинство: «Психо», «Печать
        зла», «Дедвуд (телесериал)» лежат ровно там, где их и ждёшь. Но не все: «Восхождение»
        голым именем — страница значений, а «Кингсман: Секретная служба» на ru.wikipedia
        подписана латиницей («Kingsman: Секретная служба»), и никаким перебором уточнений в
        неё не попасть. Тогда спрашиваем поиском самой Википедии — он эти случаи и разводит.

        Разбор описки (:meth:`WikiSpelling.look`) - для имени, названного НЕ ТАК, как подписана
        статья. Он идёт не следом за поиском, а ВМЕСТЕ с ним, одной волной
        (:meth:`_asked_otherwise`): очереди из трёх кругов по сети бюджет справки не вмещает.

        Последний шаг (:attr:`catalogue`) - офлайн-карта русских прокатных имён IMDb. Она
        идёт в одной волне с запасным поиском: отвечает за картину без русской статьи и
        разводит несколько точных омонимов по измеренной известности.
        """
        kind = "сериал" if series else "фильм"
        names = titles_for(title, None)
        if series:  # у сериала своя статья, и лежит она под своим уточнением
            names.sort(key=lambda name: "сериал" not in name)
        payload = self.client.get(WIKI_HOST, WIKI_PATH, extract_params(names), {}, timeout)
        hops, pages = wiki_pages(payload)
        direct = _own_name_first([_article(name, hops, pages) for name in names], title)
        found = read_origin(direct, title, trusted=True, series=series)
        if found:
            return found
        found = redirected_name(names, hops, pages, title)
        if found:
            return found
        return self._asked_otherwise(title, series, kind, timeout) or self.catalogue.look(
            title, series
        )

    def _asked_otherwise(self, title: str, series: bool, kind: str, timeout: float) -> Origin:
        """Поиск Википедии и разбор описки - одной волной, а не друг за другом.

        🔴 TC-493. Оба шага нужны там, где прямая выборка по имени промолчала, и оба стоят по
        кругу сети. Пока они шли очередью, ответ на имя, написанное НЕ ТАК, как подписана
        статья, приезжал третьим кругом, - а третьего круга в бюджете справки нет. Замер на
        живой Википедии, «Эксперименты Лэйн» против «эксперименты лейн»: выборка 0.42 с, поиск
        0.59 с, разбор описки 0.43 с, итого 1.44 с при потолке 1.5 с и потолке одного запроса
        1.2 с: очередь из трёх кругов в обещанное не влезает ПО ПОСТРОЕНИЮ, а не по
        невезению. Человек читал это как «картины нет»: то же аниме, набранное как подписана
        статья, отвечало за 0.35 с и находилось сорока восемью раздачами.

        Волной кругов остаётся два, и написание имени перестаёт решать, доедет ли оригинал.

        Порядок доверия прежний: слово поиска сильнее догадки по сходству, и разбор описки
        отдаётся только тогда, когда поиск промолчал. Меняется цена: там, где поиск ответил,
        запросы разбора описки всё равно ушли. Платится это лишь на пути, где прямая выборка
        УЖЕ промахнулась (счастливый путь сюда не заходит вовсе), а на нём поиск и так
        собирается на второй круг по индексерам.

        Молчание любого пути - не беда всей справки: ошибка одного шага не должна отнимать
        ответ у другого, поэтому каждый идёт своим потоком и своё исключение глотает сам.

        Все нитки подняты здесь, значит и закрыты будут здесь (:func:`closed_wave`): срок
        отдаёт ответ спрашивающему, а брошенная нитка доживала бы своё уже в чужой работе.
        Платит закрытие фоновая нитка паспорта, которая сюда и позвала, - не человек:
        его потолок держит :meth:`~torrcast.usecases.passport.Passport._typed`.
        """
        box: dict[str, Origin] = {}
        searched: list[JsonValue] = []

        def by_search() -> None:
            with contextlib.suppress(Exception):
                params = search_params(f"{title} {kind}")
                payload = self.client.get(WIKI_HOST, WIKI_PATH, params, {}, timeout)
                searched.extend(wiki_ranked(payload))

        def by_spelling() -> None:
            with contextlib.suppress(Exception):
                box["spelling"] = self.spelling.look(title, series, timeout)

        def by_map() -> None:
            with contextlib.suppress(Exception):
                box["map"] = self.catalogue.look(title, series)

        deadline = time.monotonic() + timeout
        wave = [
            threading.Thread(target=work, daemon=True) for work in (by_search, by_spelling, by_map)
        ]
        for thread in wave:
            thread.start()
        return closed_wave(wave, deadline, lambda: self._wave_answer(searched, box, title, series))

    def _wave_answer(
        self, pages: Sequence[JsonValue], box: dict[str, Origin], title: str, series: bool
    ) -> Origin:
        """Take the strongest answer that reached the shared deadline."""
        searched = self._ranked_origin(pages, title, series, box.get("map", Origin()))
        return searched or box.get("spelling") or box.get("map") or Origin()

    def _ranked_origin(
        self, pages: Sequence[JsonValue], title: str, series: bool, known: Origin
    ) -> Origin:
        """Prefer the best-known exact namesake, while keeping Wikipedia's identity.

        Search rank is allowed to change and has put a little-known same-titled film
        above the famous one.  The offline map already resolves exact Russian names by
        IMDb vote count.  Its year selects among accepted Wikipedia articles; the
        article still supplies the title and QID.  With no map match, search order stays
        authoritative rather than turning absence of evidence into a guess.
        """
        found = [read_origin([page], title, series=series) for page in pages]
        candidates = [origin for origin in found if origin]
        if len(candidates) < 2:
            return candidates[0] if candidates else Origin()
        if known.year is None:
            return candidates[0]
        return next(
            (
                origin
                for origin in candidates
                if origin.year is not None and abs(origin.year - known.year) <= 1
            ),
            candidates[0],
        )
