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
* оригинальное имя спрашивается у подсказчика, и годится только тот ответ, который
  источник назвал ТЕМ ЖЕ именем, каким спросили, - и только если он один такой.

Молчание тут - ответ, а не отказ: строка остаётся строкой, и битой плитки не бывает.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Final
from urllib.parse import quote

from torrcast.adapters.wiki.poster_bodies import PosterBodies
from torrcast.adapters.wiki.poster_files import POSTER_WIDTH
from torrcast.domain.facts.ask import Ask
from torrcast.domain.slugify import slugify
from torrcast.ports.bytes_client import BytesClient
from torrcast.ports.json_client import JsonClient
from torrcast.ports.title_ids import TitleIds

#: Хост подсказчика; тот же, который спрашивает поле поиска на самом imdb.com.
_HOST: Final = "v3.sg.media-imdb.com"
#: Какие роды IMDb считаются нашими двумя. Серия сериала, игра и клип - не картины вовсе,
#: и обложка игры под именем одноимённого фильма была бы ровно той чужой картинкой.
_KINDS: Final = {
    "movie": frozenset({"movie", "tvMovie", "tvSpecial", "short", "video"}),
    "tv": frozenset({"tvSeries", "tvMiniSeries"}),
}
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
        if ask.year is None or ask.kind not in _KINDS:
            return []
        # Карта назвала id, а картинки у него нет - тогда второй путь: у «Паразиты» 2016
        # обложка лежит под тем же оригинальным именем, каким картину зовёт сам источник.
        row = self._by_id(known, timeout) if known else None
        return _sized(_image(row or self._by_name(ask, timeout)))

    def _by_id(self, known: str, timeout: float) -> dict[str, Any] | None:
        """Картинка названного id; год и род сверила карта, сверять их снова нечем.

        Строка без картинки тут - не ответ, а пустота: у неё нечего показывать, и звать
        её ответом значило бы закрыть картине второй путь.
        """
        rows = self._rows(known, timeout)
        return next((row for row in rows if row.get("id") == known and _image(row)), None)

    def _by_name(self, ask: Ask, timeout: float) -> dict[str, Any] | None:
        """Единственная картина, которую источник назвал ровно тем именем, каким спросили.

        Спрашивается ОРИГИНАЛЬНОЕ имя, а не русское, и это не забывчивость. Своим именем
        (поле ``l``) IMDb называет картину латиницей всегда, поэтому русское имя тут не
        совпало бы ни с чем и годился бы любой ответ ранжировщика - ровно то, чем чужая
        картинка и приезжает. Русское имя спрашивается у карты (:meth:`_known`), где оно
        сверено с годом и родом.
        """
        text = ask.original.strip()
        if not text:
            return None
        rows = [
            row
            for row in self._rows(text, timeout)
            if _fits(ask, row) and slugify(str(row.get("l") or "")) == slugify(text)
        ]
        return rows[0] if len({str(row.get("id")) for row in rows}) == 1 else None

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


def _fits(ask: Ask, row: dict[str, Any]) -> bool:
    """Годится ли эта картина IMDb под просьбу: род и год сверены точно.

    Год сверяется РОВНО, без допуска. Допуск стоил бы дороже, чем даёт: у сериала
    подсказчик называет год начала, и «сдвинуться на единицу» означало бы пустить соседний
    сезон чужой картины, а такая ошибка человеку видна, в отличие от пропущенной картинки.
    """
    return bool(
        str(row.get("id", "")).startswith("tt")
        and _image(row)
        and str(row.get("qid", "")) in _KINDS[ask.kind]
        and row.get("y") == ask.year
    )


def _image(row: dict[str, Any] | None) -> str:
    """Адрес картинки этой картины; её у IMDb нет - пустая строка."""
    picture = row.get("i") if isinstance(row, dict) else None
    found = picture.get("imageUrl") if isinstance(picture, dict) else None
    return found if isinstance(found, str) else ""


def _sized(address: str) -> list[str]:
    """Тот же постер шириной с остальные, а следом - как есть.

    Сырой адрес отдаёт исходник в несколько мегабайт: столько к человеку в список едет
    десяток раз. Ширину просят прямо в имени файла, и оба адреса называются по порядку -
    ужатый отдельно не существует, но правило имён у чужого хоста может и смениться.
    """
    small = re.sub(r"\._V1_[^/]*\.jpg$", f"._V1_UX{POSTER_WIDTH}_.jpg", address)
    return list(dict.fromkeys(one for one in (small, address) if one))
