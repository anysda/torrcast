"""Постер картины из IMDb: второй источник картинок, после Википедии.

Зачем второй вообще. Потолок одной Википедии измерен, и он ниже планки: статьи там просто
НЕТ у «Паразиты» 1999, у «Решала: Брат», у «8 дней: до Луны и обратно», у «Властелин»
1999. Это не промах разбора, который можно починить: страницы нет, и брать картинку негде.

Ключа тут нет, и человеку добывать нечего: подсказчик IMDb отвечает по тому же адресу, по
которому ходит поле поиска на их собственном сайте, а картинку отдаёт ``m.media-amazon.com``.
Кинопоиск и TMDB вычеркнуты не только словом владельца: их хосты с этой сети не
разрешаются вовсе, а постер со страницы трекера вычеркнут отдельно - его тянул бы клиент
Home Assistant через сеть, где режут по SNI.

🔴 Чужая картинка хуже отсутствующей, и весь разбор тут - про отказ. Подсказчик ранжирует
по популярности: на «Брат» он отдаёт индийскую картину впереди польской, а на «Брат» без
года - «Father Mother Sister Brother», потому что английское имя нашей картины лежит
внутри чужого. Поэтому имя картины НИКОГДА не ищется на глазок:

* русское прокатное имя спрашивается у офлайн-карты выгрузки IMDb - она отвечает
  единственным id на точную тройку «имя, год, род» и молчит, если id не один;
* имя латиницей (``original``, а нет его - собственный титул) спрашивается у подсказчика,
  и годится либо ответ, названный источником ТЕМ ЖЕ именем, либо - только если он один
  такой - ответ на ПОЛНОЕ другое имя картины: подсказчик разрешает и вторые названия
  («Un dramma borghese» в «Mimi»), а вот однословный текстовый промах вроде «Brat»
  («Father Mother Sister Brother») по-прежнему отсекается (:mod:`~torrcast.adapters.wiki.
  imdb_rows`).

Молчание тут - ответ, а не отказ: строка остаётся строкой, и битой плитки не бывает.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Final
from urllib.parse import quote

from torrcast.adapters.wiki import imdb_rows
from torrcast.adapters.wiki.poster_bodies import PosterBodies
from torrcast.domain.facts.ask import Ask
from torrcast.domain.said_in_latin import _said_in_latin
from torrcast.ports.bytes_client import BytesClient
from torrcast.ports.json_client import JsonClient
from torrcast.ports.title_ids import TitleIds

#: Хост подсказчика; тот же, который спрашивает поле поиска на самом imdb.com.
_HOST: Final = "v3.sg.media-imdb.com"
#: Сколько картин спрашивается разом: у списка находок их десяток.
_LANES: Final = 6
#: Сколько ждём один ответ подсказчика. Он отвечает за 0.2-0.5 с, и ждать дольше нечего:
#: за молчанием тут стоит не долгий поиск, а обрыв.
_ASK_TIMEOUT: Final = 4.0


class ImdbPoster:
    """Цепочка за постером IMDb: сверенный id, потом его картинка, потом байты."""

    def __init__(
        self, client: JsonClient, files: BytesClient, catalogue: TitleIds | None = None
    ) -> None:
        self.client = client
        self.catalogue = catalogue
        self.pictures = PosterBodies(files)

    def poster(self, ask: Ask, timeout: float) -> bytes | None:
        """Байты постера одной картины; постера у неё нет - ``None``."""
        return self.bodies(self.wanted([ask], timeout), timeout).get(ask)

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        """Кому есть что показывать: готовые адреса постеров на каждую картину."""
        if not asks:
            return {}
        known = self._known(asks)
        with ThreadPoolExecutor(max_workers=_LANES) as lanes:
            got = list(
                lanes.map(lambda ask: self._addresses(ask, known.get(ask, ""), timeout), asks)
            )
        return dict(zip(asks, got, strict=True))

    def bodies(self, wanted: dict[Ask, list[str]], timeout: float) -> dict[Ask, bytes]:
        """Байты постеров по названным адресам; шаг общий у всех источников картинок."""
        return self.pictures.bodies(wanted, timeout)

    def _known(self, asks: Sequence[Ask]) -> dict[Ask, str]:
        """IMDb-id по русскому прокатному имени; карта лежит на диске, сети тут нет.

        🔴 Тёзка по имени и году, разошедшийся только родом, спрашивается у карты не
        поимённо: карта отвечает на пару «имя, год», и «Зона отчуждения. Финал» 2019
        приехал бы сериалу с id фильма. Такие пары не спрашиваются вовсе - у них есть
        второй путь, по оригинальному имени.
        """
        if self.catalogue is None:
            return {}
        counted = [(ask.title, ask.year) for ask in asks]
        alone = [ask for ask in asks if counted.count((ask.title, ask.year)) == 1 and ask.year]
        try:
            found = self.catalogue.ids([(ask.title, ask.year, ask.kind) for ask in alone])
        except Exception:
            return {}
        pairs = ((ask, (ask.title, ask.year)) for ask in alone)
        return {ask: found[pair] for ask, pair in pairs if pair in found}

    def _addresses(self, ask: Ask, known: str, timeout: float) -> list[str]:
        """Адреса постера одной картины; сверить её не по чем или не с чем - пусто.

        🔴 Без года не спрашиваем вовсе. Год - единственное, чем тёзки тут отличаются друг
        от друга: подсказчик не знает ни режиссёра, ни страны, и «Паразиты» без года
        означали бы «любые из семи».
        """
        if ask.year is None or ask.kind not in imdb_rows.KINDS:
            return []
        # Карта назвала id, а картинки у него нет - тогда второй путь: у «Паразиты» 2016
        # обложка лежит под тем же оригинальным именем, каким картину зовёт сам источник.
        row = self._by_id(known, timeout) if known else None
        return imdb_rows._sized(imdb_rows._image(row or self._by_name(ask, timeout)))

    def _by_id(self, known: str, timeout: float) -> dict[str, Any] | None:
        """Картинка названного id; год и род сверила карта, сверять их снова нечем.

        Строка без картинки тут - не ответ, а пустота: у неё нечего показывать, и звать
        её ответом значило бы закрыть картине второй путь.
        """
        rows = self._rows(known, timeout)
        return next((row for row in rows if row.get("id") == known and imdb_rows._image(row)), None)

    def _by_name(self, ask: Ask, timeout: float) -> dict[str, Any] | None:
        """Единственная картина, которую источник назвал ровно тем именем, каким спросили.

        Спрашивается имя, сказанное ЛАТИНИЦЕЙ: своим именем (поле ``l``) IMDb называет
        картину латиницей всегда, и русское тут не совпало бы ни с чем - годился бы любой
        ответ ранжировщика. Русское спрашивается у карты (:meth:`_known`), с годом и родом.

        🔴 Латинское имя не всегда лежит в ``original``: поле заполняется только там, где
        имён ДВА (:func:`torrcast.domain.picture_tile.picture_tile`), и пока спрашивалось
        одно оно, картина с ОДНИМ именем не спрашивалась тут ни разу. Замер 07-09-2026 на
        живых полках стенда: из 25 плиток без обложки 17 получили её по собственному титулу
        («Bob's Burgers», «Doraemon»), и планка §9 ТЗ в 60% без них не берётся.
        """
        text = ask.original.strip() or (ask.title.strip() if _said_in_latin(ask.title) else "")
        if not text:
            return None
        rows = [row for row in self._rows(text, timeout) if imdb_rows._fits(ask, row)]
        exact = [row for row in rows if imdb_rows._same_name(text, row)]
        # Тёзка по другому имени - тоже она, если подсказчик привёл ровно её одну: вторые
        # названия он разрешает сам, и «Un dramma borghese» честно приезжает «Mimi».
        chosen = exact or imdb_rows._otherwise_named(text, rows)
        return chosen[0] if len({str(row.get("id")) for row in chosen}) == 1 else None

    def _rows(self, text: str, timeout: float) -> list[dict[str, Any]]:
        """Ответ подсказчика на одно имя; сеть промолчала - пустота, а не исключение.

        Пустота тут значит «картинки этой картине не нашлось», и это верно даже при
        обрыве: источник ВТОРОЙ, и его молчание не должно стирать ответ первого. Промах
        зовущий откладывает на свои пять минут (:data:`hass.hit_posters._RETRY`).
        """
        path = "/suggestion/x/" + quote(text, safe="") + ".json"
        try:
            got = self.client.get(
                _HOST, path, {"includeVideos": "0"}, {}, min(timeout, _ASK_TIMEOUT)
            )
        except Exception:
            return []
        found = got.get("d") if isinstance(got, dict) else None
        return [row for row in found if isinstance(row, dict)] if isinstance(found, list) else []
