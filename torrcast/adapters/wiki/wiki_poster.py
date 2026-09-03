"""Постер картины из английской Википедии; зовут карточка плеера и список обзора.

Путь разложен на два шага, и это не украшение. ПЕРВЫЙ отвечает на вопрос «есть ли у этой
картины статья с подтверждённым годом» (:class:`~torrcast.adapters.wiki.poster_pages.PosterPages`),
ВТОРОЙ приносит байты. Разделены они потому, что имя картинки нельзя выдавать раньше
ответа на первый вопрос: человек видит рамку вокруг пустоты там, где строка должна была
остаться строкой (TC-1023).

Оба шага берут пачку картин целиком: у списка находок их десяток, и десяток отдельных
цепочек по три запроса каждая - это стук по Википедии, а не поиск.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Final

from torrcast.adapters.wiki.endpoints import EN_WIKI_HOST, WIKI_PATH
from torrcast.adapters.wiki.poster_pages import PosterPages
from torrcast.domain.facts.ask import Ask
from torrcast.domain.facts.in_budget import in_budget
from torrcast.domain.facts.infobox_image import infobox_image
from torrcast.domain.facts.poster_address import poster_address
from torrcast.domain.facts.wiki_pages import wiki_pages
from torrcast.domain.json_map import json_map
from torrcast.domain.json_value import JsonValue
from torrcast.ports.bytes_client import BytesClient
from torrcast.ports.json_client import JsonClient

#: Ширина копии постера, точек. Карточка плеера рисует её в пару сотен, а Wikimedia
#: отдаёт растр любой ширины - и вектор тоже (у сериалов в ``image`` лежит логотип).
POSTER_WIDTH: Final = 500
#: Сколько имён влезает в один запрос ``titles``: предел API для гостя.
_TITLES: Final = 50
#: Сколько знаков имён везёт адрес запроса; длиннее - «414 URI Too Long».
_BUDGET: Final = 6000
#: Сколько картинок качается разом. Сами байты - самый долгий шаг из всех: запросов на
#: список уходит четыре, а картинок десяток, и подряд они складывались бы в секунды.
_LANES: Final = 4


class WikiPoster:
    """Цепочка за постером: английская статья со сверенным годом, инфобокс, файл, байты.

    Ни ключа, ни регистрации, ни одного нового хоста сверх тех, куда справка ходит и
    так. Каталоги метаданных (Кинопоиск, TMDB) вычеркнуты требованием владельца - «без
    ключей и всякого такого», - а постер со страницы трекера вычеркнут отдельно: адрес
    вёл бы на хост трекера, и картинку тянул бы клиент Home Assistant через сеть, где
    режут по SNI.

    🔴 Сеть тут оставляется исключением, а не пустотой. «Постера нет» и «Википедия не
    ответила» - разные ответы: первый честно означает, что этой картине картинки не
    найти, а второй означает 429 или обрыв, после которого спрашивать можно снова.
    Различает их вызывающий (:class:`hass.posters.Posters`), и обоим у него один и тот
    же запасной путь - кадр из показа.
    """

    def __init__(self, client: JsonClient, files: BytesClient) -> None:
        self.client = client
        self.files = files
        self.pages = PosterPages(client)

    def poster(self, ask: Ask, timeout: float) -> bytes | None:
        """Байты постера одной картины; статьи нет или инфобокс без картинки - ``None``.

        Дверь для карточки играющего: картина там одна, и пачка из неё одной - это те же
        шаги в том же порядке. Правило у карточки и у списка обзора обязано быть одно,
        иначе человек увидит в списке не ту картинку, что потом заиграет.
        """
        return self.bodies(self.wanted([ask], timeout), timeout).get(ask)

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        """Кому вообще есть что показывать: статьи со сверенным годом на каждую картину.

        Пустой список тут - это ответ, а не отказ: у картины нет статьи ни под своим
        именем, ни под оригинальным, и картинки ей взять неоткуда.
        """
        return self.pages.wanted(asks, timeout)

    def bodies(self, wanted: dict[Ask, list[str]], timeout: float) -> dict[Ask, bytes]:
        """Байты постеров по отобранным статьям; вся пачка за три запроса и загрузки.

        Инфобоксы всех статей читаются одним запросом, адреса всех файлов - вторым:
        поштучно это было бы до трёх ``parse`` на каждую находку, то есть тридцать
        запросов на список из десяти.
        """
        pages = list(dict.fromkeys(page for rows in wanted.values() for page in rows))
        if not pages:
            return {}
        files = self._images(pages, timeout)
        addresses = self._addresses(list(dict.fromkeys(files.values())), timeout)
        picked = {
            ask: next(
                (addresses[files[page]] for page in rows if addresses.get(files.get(page, ""))),
                "",
            )
            for ask, rows in wanted.items()
        }
        wanted_addresses = list(dict.fromkeys(one for one in picked.values() if one))
        with ThreadPoolExecutor(max_workers=_LANES) as lanes:
            loaded = dict(
                zip(
                    wanted_addresses,
                    lanes.map(lambda one: self._body(one, timeout), wanted_addresses),
                    strict=True,
                )
            )
        return {ask: body for ask, one in picked.items() if (body := loaded.get(one)) is not None}

    def _body(self, address: str, timeout: float) -> bytes | None:
        return self.files.fetch(address, timeout) if address else None

    def _images(self, pages: Sequence[str], timeout: float) -> dict[str, str]:
        """Имя файла постера по имени статьи: вики-текст ПЕРВОЙ секции пачкой.

        Секция названа номером не ради экономии: полная статья везёт сотни килобайт
        разметки, а ``| image =`` лежит в первых её строках. Читается она через
        ``revisions``, а не ``parse``, ровно потому, что ``parse`` берёт одну статью за
        запрос, а ``revisions`` - полсотни.
        """
        out: dict[str, str] = {}
        for part in in_budget(pages, _TITLES, _BUDGET):
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
            hops, found = wiki_pages(self.client.get(EN_WIKI_HOST, WIKI_PATH, params, {}, timeout))
            for page in part:
                seen = page
                for _ in range(3):  # нормализация, затем перенаправление
                    seen = hops.get(seen, seen)
                name = infobox_image(_wikitext(found.get(seen)))
                if name:
                    out[page] = name
        return out

    def _addresses(self, files: Sequence[str], timeout: float) -> dict[str, str]:
        """Адрес копии постера по имени файла: ``imageinfo`` тоже берёт пачку."""
        out: dict[str, str] = {}
        for part in in_budget(files, _TITLES, _BUDGET):
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
            hops, found = wiki_pages(self.client.get(EN_WIKI_HOST, WIKI_PATH, params, {}, timeout))
            for name in part:
                seen = f"File:{name}"
                for _ in range(3):  # подчёркивания вместо пробелов, затем перенаправление
                    seen = hops.get(seen, seen)
                page = found.get(seen)
                address = poster_address({"query": {"pages": [page]}}) if page else ""
                if address:
                    out[name] = address
        return out


def _wikitext(page: JsonValue) -> str:
    """Вики-текст первой секции из ответа ``revisions``; статьи нет - пустой текст."""
    revisions = json_map(page).get("revisions")
    if not isinstance(revisions, list) or not revisions:
        return ""
    slots = json_map(json_map(revisions[0]).get("slots"))
    return str(json_map(slots.get("main")).get("content") or "")
