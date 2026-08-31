"""Добор справки к меню: Википедия, Wikidata и выгрузка оценок; зовёт сценарий меню."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable

from torrcast.adapters.wiki.closed_wave import closed_wave
from torrcast.adapters.wiki.endpoints import (
    SPARQL_HEAD,
    WIKI_HOST,
    WIKIDATA_HOST,
    WIKIDATA_PATH,
)
from torrcast.adapters.wiki.spoken_blurbs import spoken_blurbs
from torrcast.adapters.wiki.wiki_extracts import wiki_extracts
from torrcast.adapters.wiki.wiki_host import wiki_host
from torrcast.domain.catalogs.tongue import tongue
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.hms import hms
from torrcast.domain.facts.read_pages import _read_pages
from torrcast.domain.facts.read_sparql import read_sparql
from torrcast.domain.facts.settings import HTTP_TIMEOUT
from torrcast.ports.json_client import JsonClient
from torrcast.ports.rating_dump import RatingDump
from torrcast.ports.title_ids import TitleIds


class WikiBlurbs:
    """Два сетевых шага и файл оценок; отказ второго шага не отменяет первого."""

    def __init__(
        self, client: JsonClient, ratings: RatingDump, catalogue: TitleIds | None = None
    ) -> None:
        self.client = client
        self.ratings = ratings
        self.catalogue = catalogue

    def fetch(
        self,
        wanted: list[tuple[str, int | None]],
        timeout: float = HTTP_TIMEOUT,
        ready: Callable[[dict[tuple[str, int | None], Fact]], None] | None = None,
        kinds: dict[tuple[str, int | None], str] | None = None,
    ) -> tuple[dict[tuple[str, int | None], Fact], set[tuple[str, int | None]]]:
        """Собрать справку по картинам: Википедия → Wikidata → выгрузка рейтингов.

        Цепочка тут не вся: Wikidata спрашивают по идентификаторам из Википедии, и эти два
        запроса иначе как друг за другом не идут. А вот выгрузка рейтингов - файл на диске, с
        сетью не связанный ничем; читалась она третьим шагом, и её сотня тысяч строк ложилась
        на те же полторы секунды дедлайна, что и оба запроса. Теперь она читается ПОКА идёт
        первый запрос и к моменту нужды уже готова.

        🔴 TC-561. Два шага стоят разного и значат разное. Первый несёт то, ради чего справку
        и зовут, - о чём кино; второй лишь украшает его рейтингом и хронометражем. А платят
        они одинаково: замер по ста меню - Википедия 0.73 с, Wikidata 0.89 с в середине и
        1.5 с на девятом дециле, то есть в сумме мимо потолка в полторы секунды чаще, чем в
        него. Раньше опоздание или отказ ВТОРОГО шага отменяли ПЕРВЫЙ целиком: исключение
        улетало наверх, добытое описание пропадало вместе с ним, и в кэш не ложилось ничего -
        следующее меню шло за тем же самым заново и снова печаталось голым (38 прогонов из
        ста не сохранили ни строки).

        Теперь порядок соответствует цене: описания отдаются ``ready`` сразу, как приехали, -
        меню печатает их, не дожидаясь украшений. Отказ Wikidata гасится: справка выходит без
        рейтинга и хронометража, но с тем, что уже добыто, и ложится в кэш.

        Второй элемент ответа - про какие картины Википедия РЕАЛЬНО ответила
        (:meth:`extracts`): только про них «статьи нет» - честный итог, и только их
        вызывающий вправе запомнить пустыми.
        """
        scores: dict[str, str] = {}
        local_ids: dict[tuple[str, int | None], str] = {}

        def load() -> None:
            nonlocal scores, local_ids
            scores = self.ratings.scores()
            if self.catalogue is not None:
                local_ids = self.catalogue.ids(
                    [
                        (title, year, (kinds or {}).get((title, year), "movie"))
                        for title, year in wanted
                    ]
                )

        reader = threading.Thread(target=load, daemon=True)
        reader.start()
        # Имена Википедий греются ЗДЕСЬ, а не там, где понадобятся: разрешать имя в
        # срок своей волны значит отдавать этот срок резолверу, а идёт волна под грохот
        # прогрева раздач (:meth:`~torrcast.ports.json_client.JsonClient.warm`). Имён два,
        # и греются оба: первая волна всегда идёт в русскую Википедию, вторая - в
        # Википедию языка продукта, и под русским языком это одно и то же имя.
        for host in dict.fromkeys([WIKI_HOST, wiki_host(tongue())]):
            self.client.warm(host)
        try:
            candidates, payload, answered = wiki_extracts(self.client, wanted, timeout, kinds)
        except OSError:
            # Википедия и локальная оценка друг от друга не зависят. Сетевой отказ не
            # вправе выбрасывать уже найденные по точным имени, году и типу IMDb-id.
            scores, local_ids = closed_wave(
                [reader], time.monotonic() + timeout, lambda: (dict(scores), dict(local_ids))
            )
            return (
                {
                    key: Fact(rating=f"IMDb {scores[tconst]}")
                    for key, tconst in local_ids.items()
                    if tconst in scores
                },
                set(),
            )
        in_time = closed_wave(
            [reader], time.monotonic() + timeout, lambda: (dict(scores), dict(local_ids))
        )
        scores, local_ids = in_time
        about, entities, linked = _read_pages(payload, candidates, set(local_ids), kinds)
        about, answered = spoken_blurbs(self.client, about, linked, answered, timeout)
        if ready is not None:
            # Первым шагом едет ВСЁ, что уже на руках, а не только картины со статьёй:
            # оценка лежит в офлайн-карте и приехала, пока шла первая волна. Придержи её
            # до второго шага - и картина без статьи теряла бы оценку, которая у нас уже
            # была: у русского показа так пропадал «Титаник: 20 лет спустя» (TC-957).
            first = {
                key: Fact(
                    about=about.get(key, ""),
                    rating=(
                        f"IMDb {scores[local_ids[key]]}" if local_ids.get(key) in scores else ""
                    ),
                )
                for key in wanted
            }
            ready({key: fact for key, fact in first.items() if fact})
        ids: dict[str, tuple[str, int]] = {}
        if entities:
            with contextlib.suppress(Exception):
                ids = self.ids(sorted(set(entities.values())), timeout)
        out: dict[tuple[str, int | None], Fact] = {}
        for key in wanted:
            imdb_id, minutes = ids.get(entities.get(key, ""), ("", 0))
            fact = Fact(
                about=about.get(key, ""),
                rating=(
                    f"IMDb {scores[local_ids.get(key, imdb_id)]}"
                    if local_ids.get(key, imdb_id) in scores
                    else ""
                ),
                runtime=hms(minutes),
            )
            if fact:
                out[key] = fact
        return out, answered

    def ids(self, items: list[str], timeout: float) -> dict[str, tuple[str, int]]:
        """Q-идентификаторы → (идентификатор IMDb, минуты). Один запрос на все картины.

        Хронометраж берём здесь, а не из выгрузки IMDb, по цене вопроса: за ``title.basics``
        пришлось бы качать 225 МБ. Расхождение с IMDb бывает в пару минут — это разница в том,
        считать ли титры, а не выдумка.

        Длительность спрашивается ВМЕСТЕ С ЕДИНИЦЕЙ, и это не украшение. ``wdt:`` отдаёт
        голое число, а величина у Wikidata с единицей: у большинства картин там минуты, у
        «Оппенгеймера» - секунды, и без единицы разобрать одно от другого нечем. Единица
        лежит не у самого свойства, а у значения утверждения (``psv:``), поэтому её
        приходится доставать отдельным шагом.

        Шаг этот - ВЛОЖЕННЫЙ ``OPTIONAL`` внутри уже имеющегося, и порядок тут значащий:
        само число как бралось у ``wdt:``, так и берётся, то есть отбор утверждений не
        меняется ни на знак; единица лишь подсаживается к нему по равенству величины.
        Не нашлась или ответ пришёл без неё - число остаётся минутами
        (:func:`~torrcast.domain.facts.read_sparql.read_sparql`), как было.
        """
        values = " ".join(f"wd:{item}" for item in items)
        query = (
            f"SELECT ?item ?imdb ?dur ?unit WHERE {{ VALUES ?item {{ {values} }} "
            "OPTIONAL { ?item wdt:P345 ?imdb } "
            "OPTIONAL { ?item wdt:P2047 ?dur . "
            "OPTIONAL { ?item p:P2047/psv:P2047 ?value . "
            "?value wikibase:quantityAmount ?dur ; wikibase:quantityUnit ?unit } } }"
        )
        payload = self.client.get(
            WIKIDATA_HOST, WIKIDATA_PATH, {"query": query}, dict(SPARQL_HEAD), timeout
        )
        return read_sparql(payload)
