"""Добор справки к меню: Википедия, Wikidata и выгрузка оценок; зовёт сценарий меню."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable
from typing import Any

from torrcast.adapters.wiki.closed_wave import closed_wave
from torrcast.adapters.wiki.endpoints import (
    SPARQL_HEAD,
    WIKI_HOST,
    WIKI_PATH,
    WIKIDATA_HOST,
    WIKIDATA_PATH,
)
from torrcast.domain.facts.extract_params import extract_params
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.hms import hms
from torrcast.domain.facts.read_pages import _read_pages
from torrcast.domain.facts.read_sparql import read_sparql
from torrcast.domain.facts.settings import _EXBATCHES, _EXLIMIT, HTTP_TIMEOUT
from torrcast.domain.facts.titles_for import titles_for
from torrcast.domain.facts.wiki_reply import _merged
from torrcast.ports.json_client import JsonClient
from torrcast.ports.rating_dump import RatingDump


class WikiBlurbs:
    """Два сетевых шага и файл оценок; отказ второго шага не отменяет первого."""

    def __init__(self, client: JsonClient, ratings: RatingDump) -> None:
        self.client = client
        self.ratings = ratings

    def fetch(
        self,
        wanted: list[tuple[str, int | None]],
        timeout: float = HTTP_TIMEOUT,
        ready: Callable[[dict[tuple[str, int | None], Fact]], None] | None = None,
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

        def load() -> None:
            nonlocal scores
            scores = self.ratings.scores()

        reader = threading.Thread(target=load, daemon=True)
        reader.start()
        about, entities, answered = self.extracts(wanted, timeout)
        if ready is not None:
            ready({key: Fact(about=text) for key, text in about.items() if text})
        ids: dict[str, tuple[str, int]] = {}
        if entities:
            with contextlib.suppress(Exception):
                ids = self.ids(sorted(set(entities.values())), timeout)
        # Нитку выгрузки подняли здесь - здесь и закрываем: платит это фоновый добор,
        # который сюда позвал, а меню отпущено своим потолком задолго до нас.
        in_time = closed_wave([reader], time.monotonic() + timeout, lambda: scores)
        out: dict[tuple[str, int | None], Fact] = {}
        for key in wanted:
            imdb_id, minutes = ids.get(entities.get(key, ""), ("", 0))
            fact = Fact(
                about=about.get(key, ""),
                rating=f"IMDb {in_time[imdb_id]}" if imdb_id in in_time else "",
                runtime=hms(minutes),
            )
            if fact:
                out[key] = fact
        return out, answered

    def extracts(
        self, wanted: list[tuple[str, int | None]], timeout: float
    ) -> tuple[
        dict[tuple[str, int | None], str],
        dict[tuple[str, int | None], str],
        set[tuple[str, int | None]],
    ]:
        """Одним запросом: описания по-русски и Q-идентификаторы Wikidata для второго шага.

        Кандидатов на статью у картины около десятка (:func:`titles_for`), а в один запрос их
        влезает :data:`_EXLIMIT`. Побеждает первый кандидат, который оказался статьёй (не
        страницей значений, не пустышкой) и подтвердил год (:func:`confirms`).

        🔴 TC-561. Пока запрос был один, лишние кандидаты просто отбрасывались - и это стоило
        не времени, а самой справки: в меню из семи картин до Википедии доезжало по два-три
        имени из двенадцати, то есть без уточнения «(мультфильм)», под которым и лежит
        «Моана». Замер на корпусе из ста настоящих меню (503 картины): спрошенные по одной,
        статью имеют 49% картин, а пакетом из двадцати имён справку получали 14%.

        Поэтому имена режутся на пакеты по :data:`_EXLIMIT` и уезжают РАЗОМ (:data:`_EXBATCHES`
        штук): запросы ждут сеть, а не друг друга. Замер там же: один пакет 0.78 с, три
        очередью 2.14 с, три разом 0.83 с - втрое больше имён за семь сотых секунды.

        Третий элемент ответа - про какие картины ответ приехал ПОЛНЫМ: все имена картины
        попали в пакеты, которые ответили. Промолчавший пакет не говорит про свои имена
        ничего, и картина из него - не «статьи нет», а «не успели спросить» (🔴 TC-568).
        """
        candidates = {key: titles_for(*key) for key in wanted}
        names: list[str] = []
        scheduled: dict[tuple[str, int | None], list[str]] = {key: [] for key in wanted}
        room = _EXLIMIT * _EXBATCHES
        for depth in range(max((len(c) for c in candidates.values()), default=0)):
            for key in wanted:
                if depth < len(candidates[key]) and len(names) < room:
                    names.append(candidates[key][depth])
                    scheduled[key].append(candidates[key][depth])
        answers: list[tuple[list[str], Any]] = []
        lock = threading.Lock()

        def ask(part: list[str]) -> None:
            with contextlib.suppress(Exception):
                payload = self.client.get(WIKI_HOST, WIKI_PATH, extract_params(part), {}, timeout)
                with lock:
                    answers.append((part, payload))

        parts = [names[at : at + _EXLIMIT] for at in range(0, len(names), _EXLIMIT)]
        deadline = time.monotonic() + timeout
        wave = [threading.Thread(target=ask, args=(part,), daemon=True) for part in parts]
        for thread in wave:
            thread.start()
        answers = closed_wave(wave, deadline, lambda: list(answers))
        if not answers:
            # Ни один пакет не ответил - это отказ сети, а не «статьи нет». Разница дорогая:
            # пустой ответ лёг бы в кэш на неделю и накрыл бы картину, про которую Википедия
            # прекрасно знает.
            raise OSError("Википедия не ответила ни на один запрос")
        heard = {name for part, _payload in answers for name in part}
        answered = {
            key
            for key in wanted
            if scheduled[key] and all(name in heard for name in scheduled[key])
        }
        about, entities = _read_pages(_merged([payload for _part, payload in answers]), candidates)
        return about, entities, answered

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
