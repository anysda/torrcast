"""Адрес постера по найденным статьям картины; зовёт адаптер постера.

🔴 Разделов тут ДВА, и это вся суть единицы. Английская статья кладёт свою обложку в
``| image =`` инфобокса, но кладёт не всегда: у «Чернобыль. Зона отчуждения» статья
есть, год сходится, а строка ``| image =`` в ней ПУСТА. Русская статья той же картины
на своём месте (``| изображение =``) постер держит, и файл этот лежит на русском хосте:
``en.wikipedia.org`` отвечает про него ``missing``. Поэтому и спрашиваются оба раздела,
и файл каждого разрешается на СВОЁМ хосте.

Оба шага берут пачку целиком: у списка находок десяток картин, и поштучно это было бы
до трёх запросов на каждую вместо четырёх на весь список.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Final

from torrcast.adapters.wiki.endpoints import EN_WIKI_HOST, WIKI_HOST, WIKI_PATH
from torrcast.domain.facts.dated import Dated
from torrcast.domain.facts.in_budget import in_budget
from torrcast.domain.facts.infobox_image import infobox_image
from torrcast.domain.facts.poster_address import poster_address
from torrcast.domain.facts.wiki_pages import wiki_pages
from torrcast.domain.json_map import json_map
from torrcast.domain.json_value import JsonValue
from torrcast.ports.json_client import JsonClient

#: Ширина копии постера, точек. Карточка плеера рисует её в пару сотен, а Wikimedia
#: отдаёт растр любой ширины - и вектор тоже (у сериалов в ``image`` лежит логотип).
POSTER_WIDTH: Final = 500
#: Сколько имён влезает в один запрос ``titles``: предел API для гостя.
_TITLES: Final = 50
#: Сколько знаков имён везёт адрес запроса; длиннее - «414 URI Too Long».
_BUDGET: Final = 6000
#: Сколько разделов спрашивается разом: английский и русский, и ждать их по очереди
#: значило бы удвоить ожидание человека перед списком.
_LANES: Final = 2

#: Шаг, который делается на обоих разделах одинаково: хост, пачка имён, срок.
Step = Callable[[str, Sequence[str], float], dict[str, str]]


class PosterFiles:
    """Имя файла постера и его адрес, спрошенные у обоих разделов сразу."""

    def __init__(self, client: JsonClient) -> None:
        self.client = client

    def addresses(
        self, rows: Sequence[Dated], timeout: float
    ) -> tuple[dict[Dated, str], dict[Dated, str]]:
        """Адреса постеров: сперва английские, отдельно от них - русские.

        🔴 Половины возвращаются ПОРОЗНЬ, а не слитой на строку. Слитая ставила русскую
        обложку неподходящей статьи впереди английской обложки подходящей: у запроса
        «Чернобыль» 2019 года первым кандидатом идёт «Зона отчуждения» (её категории
        называют и 2014, и 2019), и своей русской картинкой она перебивала постер
        мини-сериала HBO, стоящего кандидатом вторым. Выбор между половинами - дело
        зовущего (:meth:`~torrcast.adapters.wiki.wiki_poster.WikiPoster.wanted`), и он
        берёт русскую только тогда, когда английской нет НИ У ОДНОГО кандидата.
        """
        there, here = self._both(
            self._named,
            [row.page for row in rows if row.page],
            [row.source for row in rows if row.source],
            timeout,
        )
        at_there, at_here = self._both(
            self._where,
            list(dict.fromkeys(there.values())),
            list(dict.fromkeys(here.values())),
            timeout,
        )
        english = {
            row: at_there[there[row.page]] for row in rows if _has(row.page, there, at_there)
        }
        russian = {
            row: at_here[here[row.source]] for row in rows if _has(row.source, here, at_here)
        }
        return english, russian

    def _both(
        self,
        step: Step,
        english: Sequence[str],
        russian: Sequence[str],
        timeout: float,
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Один и тот же шаг на обоих разделах разом; пустой половине запроса нет."""
        with ThreadPoolExecutor(max_workers=_LANES) as lanes:
            there = lanes.submit(step, EN_WIKI_HOST, english, timeout)
            here = lanes.submit(step, WIKI_HOST, russian, timeout)
            return there.result(), here.result()

    def _named(self, host: str, pages: Sequence[str], timeout: float) -> dict[str, str]:
        """Имя файла постера по имени статьи: вики-текст ПЕРВОЙ секции пачкой.

        Секция названа номером не ради экономии: полная статья везёт сотни килобайт
        разметки, а строка с постером лежит в первых её строках. Читается она через
        ``revisions``, а не ``parse``, ровно потому, что ``parse`` берёт одну статью за
        запрос, а ``revisions`` - полсотни.
        """
        out: dict[str, str] = {}
        for part in in_budget(list(pages), _TITLES, _BUDGET):
            params = {
                "action": "query",
                "titles": "|".join(part),
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "rvsection": "0",
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
            }
            hops, found = self._ask(host, params, timeout)
            for page in part:
                seen = page
                for _ in range(3):  # нормализация, затем перенаправление
                    seen = hops.get(seen, seen)
                name = infobox_image(_wikitext(found.get(seen)))
                if name:
                    out[page] = name
        return out

    def _where(self, host: str, files: Sequence[str], timeout: float) -> dict[str, str]:
        """Адрес копии постера по имени файла: ``imageinfo`` тоже берёт пачку.

        Хост тут тот же, на котором нашлась статья, и это не мелочь: несвободная
        обложка лежит ЛОКАЛЬНО в своём разделе, и на чужом хосте она ``missing``.
        """
        out: dict[str, str] = {}
        for part in in_budget(list(files), _TITLES, _BUDGET):
            params = {
                "action": "query",
                "titles": "|".join(f"File:{name}" for name in part),
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": str(POSTER_WIDTH),
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
            }
            hops, found = self._ask(host, params, timeout)
            for name in part:
                seen = f"File:{name}"
                for _ in range(3):  # подчёркивания вместо пробелов, затем перенаправление
                    seen = hops.get(seen, seen)
                page = found.get(seen)
                address = poster_address({"query": {"pages": [page]}}) if page else ""
                if address:
                    out[name] = address
        return out

    def _ask(
        self, host: str, params: dict[str, str], timeout: float
    ) -> tuple[dict[str, str], dict[str, JsonValue]]:
        """Спросить раздел и разобрать ответ; не ответил - пустота, а не исключение.

        Молчание одного раздела тут не должно уносить второй: половина картинок лучше,
        чем ни одной, а отказ виден отложенной следующей попыткой у зовущего.
        """
        try:
            return wiki_pages(self.client.get(host, WIKI_PATH, params, {}, timeout))
        except Exception:
            return {}, {}


def _has(title: str, named: dict[str, str], found: dict[str, str]) -> bool:
    """Дошла ли эта статья до адреса: и имя файла названо, и файл нашёлся."""
    return bool(title) and title in named and named[title] in found


def _wikitext(page: JsonValue) -> str:
    """Вики-текст первой секции из ответа ``revisions``; статьи нет - пустой текст."""
    revisions = json_map(page).get("revisions")
    if not isinstance(revisions, list) or not revisions:
        return ""
    slots = json_map(json_map(revisions[0]).get("slots"))
    return str(json_map(slots.get("main")).get("content") or "")
