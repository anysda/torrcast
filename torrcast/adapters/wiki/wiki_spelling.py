"""Разбор описки: имя названо не так, как подписана статья; зовёт выборка по имени."""

from __future__ import annotations

import contextlib
import threading
from typing import Any

from torrcast.adapters.wiki.endpoints import _WIKI_HOST, _WIKI_PATH
from torrcast.domain.facts.near_name import _near_name
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.read_origin import read_origin
from torrcast.domain.facts.settings import _PHRASE_WORDS, _SUGGEST_HITS
from torrcast.domain.facts.wiki_params import _search_params
from torrcast.domain.facts.wiki_reply import _ranked
from torrcast.domain.transliterate import transliterate
from torrcast.ports.json_client import JsonClient


class WikiSpelling:
    """Подсказки Википедии и поиск по куску заголовка - одной волной."""

    def __init__(self, client: JsonClient) -> None:
        self.client = client

    def look(self, title: str, series: bool, timeout: float) -> Origin:
        """Имя названо не так, как подписана статья: описка, другая транскрипция, чужое слово.

        Третий и последний шаг справки, и ходит он только по пустому месту - когда прямая
        выборка и поиск Википедии уже промолчали. Счастливый путь сюда не заходит вовсе, так
        что бюджет справки этот шаг не трогает; на пустом же пути поиск и так собирается на
        второй круг по индексерам, и лишние доли секунды там не видны.

        Два способа спросить, оба идут разом и оба отвечают ЗАГОЛОВКАМИ, а не догадками:

        * **подсказки Википедии** (``opensearch``) - она сама правит транскрипцию:
          «Сальтберн» → «Солтберн». Спрашиваем и по-русски, и транслитом: аниме русская
          Википедия подписывает латиницей, и «ре зеро» находится только как ``re zero``
          («Re:Zero. Жизнь с нуля в альтернативном мире»);
        * **поиск по заголовкам без одного слова** (``intitle:``) - для имени, в котором
          человек одно слово помнит не то: «мужчина который удивил всех» ищется как
          ``intitle:"который удивил всех"`` и приводит к «Человек, который удивил всех».

        Найденное сверяется :func:`_near_name` - подсказка и поиск по куску притаскивают чужое
        («Сальтерас», «Сальтенья»), а тождество имени тут никем не доказано. Прошедшее сверку
        читается как выборка по имени (``trusted``): статью назвала сама Википедия.

        ⚠️ Паспорт этого шага - БЕЗ ГОДА, по той же причине, по которой без года отвечает
        одинокий путь :func:`origin_either`. Имя тут не доказано, а лишь признано похожим, и
        цена ошибки у двух полей разная: именем добор ищет раздачи (худшее - лишние), а год
        объявлен сильнее выдачи, и неверным годом гейт молча выкидывает всю картину. У «ре
        зеро» это видно прямо: русская статья - о ранобэ 2014 года, аниме же вышло в 2016-м.
        """
        box: dict[str, list[Any]] = {}

        def suggest(key: str, query: str) -> None:
            with contextlib.suppress(Exception):
                box[key] = self.suggested(query, timeout)

        def phrase() -> None:
            with contextlib.suppress(Exception):
                box["phrase"] = self.by_phrase(title, timeout)

        latin = transliterate(title)
        work = [
            threading.Thread(target=suggest, args=("ru", title), daemon=True),
            threading.Thread(target=phrase, daemon=True),
        ]
        if latin.lower() != title.lower():
            work.append(threading.Thread(target=suggest, args=("latin", latin), daemon=True))
        for thread in work:
            thread.start()
        for thread in work:
            thread.join(timeout)
        seen: set[str] = set()
        pages: list[Any] = []
        for key in ("ru", "latin", "phrase"):
            for page in box.get(key, []):
                heading = str(page.get("title") or "")
                if heading in seen or not _near_name(title, heading):
                    continue
                seen.add(heading)
                pages.append(page)
        found = read_origin(pages, title, trusted=True, series=series)
        # Имя тут не доказано, а признано похожим - так и говорим паспортом, чтобы гейт добора
        # знал, на чём стоит второе имя (:attr:`Origin.guessed`).
        return Origin(title=found.title, name=found.name, guessed=bool(found))

    def suggested(self, query: str, timeout: float) -> list[Any]:
        """Подсказки Википедии по написанию имени - сразу статьями, одним запросом.

        ``opensearch`` отвечает голыми заголовками, и за их первыми фразами пришлось бы ехать
        вторым запросом - то есть вторым кругом по сети внутри и без того последнего шага.
        ``generator=prefixsearch`` - тот же самый подсказчик (``opensearch`` им и работает
        внутри), но статьи приезжают с ним разом, за один поход и те же 0.4 с.
        """
        params = {
            **_search_params(""),
            "generator": "prefixsearch",
            "gpssearch": query,
            "gpslimit": str(_SUGGEST_HITS),
            "gpsnamespace": "0",
        }
        params.pop("gsrsearch", None)
        params.pop("gsrlimit", None)
        params.pop("gsrnamespace", None)
        return _ranked(self.client.get(_WIKI_HOST, _WIKI_PATH, params, {}, timeout))

    def by_phrase(self, title: str, timeout: float) -> list[Any]:
        """Статьи, у которых в ЗАГОЛОВКЕ стоит запрос без одного крайнего слова.

        Так ловится имя, в котором человек помнит не то одно слово: «мужчина который удивил
        всех» - это «Человек, который удивил всех». Обычный поиск такое не разводит вовсе: он
        полнотекстовый, и по этому запросу первым приносит биографию актёра. Отбрасывается
        ровно одно слово с краю (голову и хвост пробуем оба), и найденное всё равно сверяется
        по словам (:func:`_near_name`) - иначе ``intitle:"воспоминание"`` притащил бы что угодно.
        """
        words = title.split()
        if len(words) < _PHRASE_WORDS:
            return []
        out: list[Any] = []
        for phrase in (" ".join(words[1:]), " ".join(words[:-1])):
            payload = self.client.get(
                _WIKI_HOST, _WIKI_PATH, _search_params(f'intitle:"{phrase}"'), {}, timeout
            )
            out.extend(_ranked(payload))
            if out:
                break
        return out
