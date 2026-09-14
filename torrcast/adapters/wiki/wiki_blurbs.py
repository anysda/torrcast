"""Добор справки к меню: Википедия, Wikidata и выгрузка оценок; зовёт сценарий меню."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable

from torrcast.adapters.wiki.closed_wave import closed_wave
from torrcast.adapters.wiki.endpoints import WIKI_HOST
from torrcast.adapters.wiki.spoken_blurbs import spoken_blurbs
from torrcast.adapters.wiki.wiki_extracts import wiki_extracts
from torrcast.adapters.wiki.wiki_host import wiki_host
from torrcast.adapters.wiki.wiki_ids import wiki_ids
from torrcast.adapters.wiki.wiki_searches import wiki_searches
from torrcast.domain.catalogs.tongue import tongue
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.hms import hms
from torrcast.domain.facts.read_pages import _heading, _read_pages
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
        foreground: bool = False,
    ) -> tuple[dict[tuple[str, int | None], Fact], set[tuple[str, int | None]]]:
        """Собрать справку по картинам: Википедия → Wikidata → выгрузка рейтингов.

        Цепочка тут не вся: Wikidata спрашивают по идентификаторам из Википедии, и эти два
        запроса иначе как друг за другом не идут. Выгрузка рейтингов - файл на диске, с
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
            candidates, payload, answered, complete = wiki_extracts(
                self.client, wanted, timeout, kinds, foreground
            )
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
        # A complete direct wave only proves that our guessed headings missed.  The
        # passport has another route, Wikipedia search, for translated and differently
        # punctuated titles.  Try it before declaring the human-facing absence.
        unresolved = sorted(complete - set(about))
        searched: set[tuple[str, int | None]] = set()
        if unresolved:
            found, replies, searched = wiki_searches(
                self.client, unresolved, timeout, kinds, foreground
            )
            headings = (
                self.catalogue.ids(
                    [
                        (_heading(name), key[1], (kinds or {}).get(key, "movie"))
                        for key, names in found.items()
                        for name in names
                    ]
                )
                if self.catalogue is not None
                else {}
            )
            for reply in replies:
                extra_about, extra_entities, extra_linked = _read_pages(
                    reply, found, set(local_ids), kinds, set(headings)
                )
                about.update(extra_about)
                entities.update(extra_entities)
                linked.update(extra_linked)
        # Only both completed paths can prove absence.  A failed search remains a
        # retryable skeleton rather than a week-long ``empty`` record on disk.
        missing = (complete & searched) - set(about)
        about, answered = spoken_blurbs(self.client, about, linked, answered, timeout)
        # Translation may fail independently of the Russian source. It must not turn
        # an otherwise known article into a cached absence.
        missing &= answered
        settled = set(about) | missing
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
                    missing=key in missing,
                    entity=entities.get(key, ""),
                )
                for key in wanted
            }
            ready({key: fact for key, fact in first.items() if fact})
        ids: dict[str, tuple[str, int]] = {}
        if entities:
            with contextlib.suppress(Exception):
                ids = self.ids(sorted(set(entities.values())), timeout, foreground)
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
                missing=key in missing,
                entity=entities.get(key, ""),
            )
            if fact:
                out[key] = fact
        return out, settled

    def ids(
        self, items: list[str], timeout: float, foreground: bool = False
    ) -> dict[str, tuple[str, int]]:
        """Добрать данные сущностей, оставив шов для проб первого шага справки."""
        return wiki_ids(self.client, items, timeout, foreground)
