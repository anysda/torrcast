"""Постер картины из английской Википедии; зовёт картинка карточки плеера."""

from __future__ import annotations

from typing import Final

from torrcast.adapters.wiki.endpoints import EN_WIKI_HOST, WIKI_HOST, WIKI_PATH
from torrcast.domain.facts.english_pages import english_pages
from torrcast.domain.facts.infobox_image import infobox_image
from torrcast.domain.facts.poster_address import poster_address
from torrcast.domain.facts.titles_for import titles_for
from torrcast.domain.json_map import json_map
from torrcast.domain.json_value import JsonValue
from torrcast.ports.bytes_client import BytesClient
from torrcast.ports.json_client import JsonClient

#: Ширина копии постера, точек. Карточка плеера рисует её в пару сотен, а Wikimedia
#: отдаёт растр любой ширины - и вектор тоже (у сериалов в ``image`` лежит логотип).
POSTER_WIDTH: Final = 500
#: Сколько имён картины спрашивается у русского раздела одним запросом. Столько же их
#: и уезжает: очередь имён складывает :func:`titles_for`, и хвост её - регистровые
#: варианты, до которых на постере дело не доходит.
_NAMES: Final = 6
#: Сколько английских статей читается на постер. Первая не всегда та: у «Брата» голое
#: имя ведёт в статью про родство, и настоящий фильм стоит вторым. Больше трёх - это
#: уже перебор чужих статей, а не поиск своей.
_PAGES: Final = 3


class WikiPoster:
    """Цепочка за постером: имя английской статьи, её инфобокс, файл, байты.

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

    def poster(self, title: str, year: int | None, kind: str, timeout: float) -> bytes | None:
        """Байты постера картины; статьи нет или инфобокс без картинки - ``None``."""
        for page in self._pages(title, year, kind, timeout)[:_PAGES]:
            name = infobox_image(self._wikitext(page, timeout))
            if not name:
                continue
            address = poster_address(self._file(name, timeout))
            if address:
                return self.files.fetch(address, timeout)
        return None

    def _pages(self, title: str, year: int | None, kind: str, timeout: float) -> list[str]:
        """Имена английских статей этой картины, в порядке доверия к именам русским.

        Ссылка на английскую статью едет тем же запросом, что и сама статья, и стоит
        поэтому ноль лишних походов: ``langlinks`` с ``lllang=en`` - ровно то, чем
        справка добирает оригинальное имя (:func:`extract_params`).
        """
        names = titles_for(title, year, kind)[:_NAMES]
        if not names:
            return []
        params = {
            "action": "query",
            "titles": "|".join(names),
            "redirects": "1",
            "prop": "langlinks|pageprops",
            "lllang": "en",
            "lllimit": str(_NAMES),
            "ppprop": "disambiguation",
            "format": "json",
            "formatversion": "2",
        }
        return english_pages(self.client.get(WIKI_HOST, WIKI_PATH, params, {}, timeout), names)

    def _wikitext(self, page: str, timeout: float) -> str:
        """Вики-текст ПЕРВОЙ секции статьи: инфобокс стоит в ней, и только в ней.

        Секция названа номером не ради экономии: полная статья везёт сотни килобайт
        разметки, а ``| image =`` лежит в первых её строках. Отказ разбора («такой
        страницы нет») приезжает в теле ответа полем ``error``, а не кодом HTTP, и
        читается тут как пустой текст - то есть как повод взять следующую статью.
        """
        params = {
            "action": "parse",
            "page": page,
            "prop": "wikitext",
            "section": "0",
            "redirects": "1",
            "format": "json",
            "formatversion": "2",
        }
        reply: JsonValue = self.client.get(EN_WIKI_HOST, WIKI_PATH, params, {}, timeout)
        return str(json_map(json_map(reply).get("parse")).get("wikitext") or "")

    def _file(self, name: str, timeout: float) -> JsonValue:
        """Ответ ``imageinfo`` про файл постера: из имени файла делается адрес."""
        params = {
            "action": "query",
            "titles": f"File:{name}",
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": str(POSTER_WIDTH),
            "format": "json",
            "formatversion": "2",
        }
        return self.client.get(EN_WIKI_HOST, WIKI_PATH, params, {}, timeout)
