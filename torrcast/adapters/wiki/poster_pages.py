"""Статьи картины, у которых ПОДТВЕРЖДЁН год; зовёт адаптер постера.

Правило тут одно на обоих зовущих - и на список находок, и на карточку играющего, -
потому что человек не должен увидеть в списке не ту картинку, что потом заиграет.

🔴 Год подтверждается дёшево и часто, а не редко и дорого. Дешевле всего его называет
само имя статьи: русский раздел держит «Паразиты (фильм, 2019)» перенаправлением, и раз
оно привело в статью - год сверен за ноль запросов. Остальным помогает Wikidata: год
выхода лежит там полем P577 и берётся на ВЕСЬ список одним запросом
(:class:`~torrcast.adapters.wiki.wikidata_years.WikidataYears`).

Не подтвердился - статьи нет. Это не строгость ради строгости: пять находок «Паразиты»
разных лет вели в одну статью 2019 года и получали один и тот же постер, а человеку
сказать, что четыре из них - не они, было нечем.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Final

from torrcast.adapters.wiki.answered import answered
from torrcast.adapters.wiki.endpoints import EN_WIKI_HOST, WIKI_HOST, WIKI_PATH
from torrcast.adapters.wiki.wikidata_years import WikidataYears
from torrcast.domain.facts.ask import Ask
from torrcast.domain.facts.dated import Dated
from torrcast.domain.facts.dated_pages import dated_pages
from torrcast.domain.facts.fits_ask import fits_ask
from torrcast.domain.facts.in_budget import in_budget
from torrcast.domain.facts.poster_names import poster_names
from torrcast.domain.facts.wiki_reply import _merged
from torrcast.domain.json_value import JsonValue
from torrcast.ports.json_client import JsonClient

#: Сколько имён влезает в один запрос ``titles``: предел API для гостя.
_TITLES: Final = 50
#: Сколько знаков имён везёт адрес запроса. Полсотни русских имён дают адрес втрое
#: длиннее восьми килобайт, и Википедия отвечает на него «414 URI Too Long».
_BUDGET: Final = 6000
#: Сколько статей отдаётся на картину. Первая не всегда та: у «Брата» голое имя ведёт в
#: статью про родство, и настоящий фильм стоит вторым.
_PAGES: Final = 3
#: Сколько статей берётся из полнотекстового поиска, когда прямая выборка пуста.
_HITS: Final = 4
#: Сколько статей на картину доходит до сверки года. Порядок кандидатов - порядок
#: доверия, а каждая лишняя статья с несказанным годом едет в общий запрос к Wikidata и
#: удлиняет его: за хвостом седьмого кандидата список ждать не должен.
_TRIED: Final = 4
#: Сколько запасных дорожек идёт разом. Больше четырёх - потому что два круга стоят
#: человеку лишней секунды перед пустым экраном; не больше восьми - потому что за
#: десятком одновременных запросов Википедия отвечает уже отказом, а отказ на этой
#: дорожке значит потерянную картинку.
_LANES: Final = 8


class PosterPages:
    """Отбор английских статей под постер: имена, ссылки, сверка года."""

    def __init__(self, client: JsonClient) -> None:
        self.client = client
        self.years = WikidataYears(client)

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[Dated]]:
        """Каждой картине - её статьи со сверенным годом; нет такой - пустой список.

        Сначала прямая выборка по составленным именам: она берёт весь список находок
        одним-двумя запросами. Кому она не ответила, тем идёт запасная дорожка -
        полнотекстовый поиск русского раздела и английская статья под оригинальным
        именем. Дорожка эта узкая по замыслу: на неё попадают единицы, а не все.

        🔴 Похода к Wikidata тут РОВНО ОДИН на весь приговор, и стоит он последним. Год
        по нему добирается разом для обеих дорожек: спроси мы дважды - список ждал бы
        два ответа медленного SPARQL вместо одного, а ждёт его человек перед экраном.
        Дорожка выбирается поэтому по тому, что известно даром: имя, год в категориях и
        род. Пойдёт по ней и тот, кого потом вытянет Wikidata, - лишний запрос там идёт
        рядом с остальными и своего времени не стоит.
        """
        asked = list(dict.fromkeys(asks))
        rows = self._direct(asked, timeout)
        late = [ask for ask in asked if not self._sure(ask, rows.get(ask, ()))]
        for ask, found in (self._late(late, timeout) if late else {}).items():
            rows[ask] = [
                *rows.get(ask, ()),
                *(one for one in found if one not in rows.get(ask, ())),
            ]
        out = self._checked({ask: names[:_TRIED] for ask, names in rows.items()}, timeout)
        return {ask: out.get(ask, [])[:_PAGES] for ask in asks}

    def _sure(self, ask: Ask, rows: Iterable[Dated]) -> bool:
        """Есть ли у картины статья, подходящая по тому, что известно ДАРОМ.

        Даром - это без похода в Wikidata: год из имени статьи или из её категорий.
        Промолчавшая о годе статья тут за ответ не считается, иначе запасная дорожка не
        пошла бы за той картиной, которой SPARQL потом откажет.
        """
        return any(row.years and fits_ask(ask, row, {}) for row in rows)

    def _direct(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[Dated]]:
        """Прямая выборка статей по составленным именам: полсотни имён за запрос."""
        named = {ask: poster_names(ask) for ask in asks}
        asked = list(dict.fromkeys(name for names in named.values() for name in names))
        parts = list(in_budget(asked, _TITLES, _BUDGET))
        with ThreadPoolExecutor(max_workers=_LANES) as lanes:
            tasks = [lanes.submit(self._ru, part, timeout) for part in parts]
        payload = _merged(answered(tasks))
        return {ask: dated_pages(payload, names) for ask, names in named.items()}

    def _late(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[Dated]]:
        """Запасная дорожка: статья под оригинальным именем и поиск русского раздела.

        Обе половины идут ОДНОВРЕМЕННО. Порознь они стоили человеку лишнего похода в
        Википедию перед пустым экраном, а нужны они одна другой не больше.

        🔴 Статья под ОРИГИНАЛЬНЫМ именем идёт первой: точное имя - признак сильнее
        догадки по похожести слов, а догадок поиск отдаёт ровно :data:`_HITS`, то есть
        весь отвод :data:`_TRIED`. Пока они стояли впереди, у «Не отступать и не
        сдаваться 3» статью с точным именем И годом вытесняли Брюс Ли, Ын Сиюнь,
        октябрь 1993-го и Лорен Аведон - постер терялся, не дойдя до Wikidata.
        """
        with ThreadPoolExecutor(max_workers=_LANES) as lanes:
            foreign = lanes.submit(self._english, asks, timeout)
            searched = list(lanes.map(lambda ask: self._searched(ask, timeout), asks))
            english = foreign.result()
        out: dict[Ask, list[Dated]] = {}
        for ask, rows in zip(asks, searched, strict=True):
            named = list(english.get(ask, ()))
            out[ask] = [*named, *[row for row in rows if row not in named]]
        return out

    def _searched(self, ask: Ask, timeout: float) -> list[Dated]:
        """Статьи, которые под это имя выбрал поиск Википедии, а не мы перебором."""
        params = {
            **_LINKS,
            "titles": "",
            "generator": "search",
            "gsrsearch": ask.title,
            "gsrlimit": str(_HITS),
            "gsrnamespace": "0",
        }
        try:
            payload = self.client.get(WIKI_HOST, WIKI_PATH, params, {}, timeout)
        except Exception:
            return []
        return dated_pages(payload, None)

    def _english(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[Dated]]:
        """Английские статьи под оригинальными именами: русской статьи бывает нет вовсе.

        «Армитаж: Двойная матрица» 2002 года в русском разделе ведёт в «Armitage III»
        1994-го - соседку, которую сверка года и отсекает, - а собственная её статья
        лежит в английском разделе ровно под оригинальным именем.
        """
        named = {ask.original.strip(): ask for ask in asks if ask.original.strip()}
        if not named:
            return {}
        params = {**_LINKS, "titles": "|".join(named), "prop": "pageprops"}
        try:
            payload = self.client.get(EN_WIKI_HOST, WIKI_PATH, params, {}, timeout)
        except Exception:
            return {}
        return {ask: dated_pages(payload, [name], linked=False) for name, ask in named.items()}

    def _checked(self, dated: dict[Ask, list[Dated]], timeout: float) -> dict[Ask, list[Dated]]:
        """Отсев статей с чужим годом; неназванные годы спрашиваются одной пачкой.

        Спрашивается Wikidata только про те статьи, которые про свой год промолчали
        сами: категории отвечают даром, а SPARQL стоит отдельного похода.
        """
        unknown = [
            row.entity
            for ask, rows in dated.items()
            for row in rows
            if ask.year and row.entity and not row.years
        ]
        known = self.years.years(unknown, timeout) if unknown else {}
        return {
            ask: [row for row in rows if fits_ask(ask, row, known)] for ask, rows in dated.items()
        }

    def _ru(self, names: Sequence[str], timeout: float) -> JsonValue:
        params = {**_LINKS, "titles": "|".join(names)}
        return self.client.get(WIKI_HOST, WIKI_PATH, params, {}, timeout)


#: Общая часть запроса: ссылка на английскую статью и идентификатор картины в Wikidata
#: едут ТЕМ ЖЕ запросом, что и сама статья, и стоят поэтому ноль лишних походов.
_LINKS: Final = {
    "action": "query",
    "redirects": "1",
    "prop": "langlinks|pageprops|categories",
    "lllang": "en",
    "lllimit": "max",
    "ppprop": "disambiguation|wikibase_item",
    "cllimit": "max",
    "clshow": "!hidden",
    "format": "json",
    "formatversion": "2",
}
