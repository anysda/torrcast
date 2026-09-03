"""Постер картины из Википедии; зовут карточка плеера и список обзора.

Путь разложен на два шага, и это не украшение. ПЕРВЫЙ отвечает на вопрос «есть ли у этой
картины постер, который можно показать», ВТОРОЙ приносит его байты. Разделены они потому,
что имя картинки нельзя выдавать раньше ответа на первый вопрос: человек видит рамку
вокруг пустоты там, где строка должна была остаться строкой (TC-1023).

🔴 Первый шаг спрашивает РОВНО ТО ЖЕ, чем потом поедут байты, - готовый адрес файла.
Раньше он спрашивал другое, «есть ли статья со сверенным годом», и расходились они на
каждой картине, у которой статья есть, а обложки в ней нет: у «Чернобыль. Зона
отчуждения» строка ``| image =`` английской статьи пуста, и приговор говорил «да» там,
где байтов не было никогда. Теперь приговор - это и есть адрес.

Оба шага берут пачку картин целиком: у списка находок их десяток, и десяток отдельных
цепочек по три запроса каждая - это стук по Википедии, а не поиск.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Final

from torrcast.adapters.wiki.poster_files import PosterFiles
from torrcast.adapters.wiki.poster_pages import PosterPages
from torrcast.domain.facts.ask import Ask
from torrcast.ports.bytes_client import BytesClient
from torrcast.ports.json_client import JsonClient

#: Сколько картинок качается разом. Сами байты - самый долгий шаг из всех: запросов на
#: список уходит полдесятка, а картинок десяток, и подряд они складывались бы в секунды.
_LANES: Final = 4


class WikiPoster:
    """Цепочка за постером: статья со сверенным годом, инфобокс, файл, байты.

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
        self.images = PosterFiles(client)

    def poster(self, ask: Ask, timeout: float) -> bytes | None:
        """Байты постера одной картины; постера у неё нет - ``None``.

        Дверь для карточки играющего: картина там одна, и пачка из неё одной - это те же
        шаги в том же порядке. Правило у карточки и у списка обзора обязано быть одно,
        иначе человек увидит в списке не ту картинку, что потом заиграет.
        """
        return self.bodies(self.wanted([ask], timeout), timeout).get(ask)

    def wanted(self, asks: Sequence[Ask], timeout: float) -> dict[Ask, list[str]]:
        """Кому есть что показывать: готовые адреса постеров на каждую картину.

        Пустой список тут - это ответ, а не отказ: у картины нет ни статьи со сверенным
        годом, ни обложки в найденной статье, и картинки ей взять неоткуда. Непустой -
        это обещание байтов, а не надежда на них: адрес уже назван источником.

        🔴 Английские обложки идут ПЕРЕД русскими, и порядок этот не про красоту языка.
        Русская обложка берётся только там, где английской нет ни у одного кандидата, -
        то есть добавляет картинки, но ни одной не подменяет. Иначе русская картинка
        первого по доверию кандидата перебивала бы английскую картинку второго, а
        первый бывает шире запроса: «Зона отчуждения» называет своими и 2014, и 2019.
        """
        rows = self.pages.wanted(asks, timeout)
        there, here = self.images.addresses(
            list(dict.fromkeys(row for one in rows.values() for row in one)), timeout
        )
        return {
            ask: list(
                dict.fromkeys(
                    [there[row] for row in one if row in there]
                    + [here[row] for row in one if row in here]
                )
            )
            for ask, one in rows.items()
        }

    def bodies(self, wanted: dict[Ask, list[str]], timeout: float) -> dict[Ask, bytes]:
        """Байты постеров по названным адресам; ни один не отдал байт - картины нет.

        Разбора тут больше нет вовсе: адреса назвал приговор, и остаётся их скачать.
        Адреса пробуются по порядку, а не один первый: приговор назвал их несколько
        именно затем, чтобы обрыв на одной картинке не оставлял плитку битой. Один и
        тот же адрес качается ОДИН раз - у сборника и его первой части постер общий.
        """
        asks = [ask for ask, one in wanted.items() if one]
        if not asks:
            return {}
        loaded: dict[str, bytes | None] = {}
        guard = threading.Lock()
        with ThreadPoolExecutor(max_workers=_LANES) as lanes:
            got = list(
                lanes.map(lambda ask: self._first(wanted[ask], timeout, loaded, guard), asks)
            )
        return {ask: body for ask, body in zip(asks, got, strict=True) if body is not None}

    def _first(
        self,
        addresses: Sequence[str],
        timeout: float,
        loaded: dict[str, bytes | None],
        guard: threading.Lock,
    ) -> bytes | None:
        """Байты первого адреса, который их отдал; молчат все - ``None``."""
        for address in addresses:
            with guard:
                seen = address in loaded
                body = loaded.get(address)
            if not seen:
                body = self._body(address, timeout)
                with guard:
                    loaded[address] = body
            if body:
                return body
        return None

    def _body(self, address: str, timeout: float) -> bytes | None:
        """Скачать один постер; сеть промолчала - пустота, а не исключение.

        Пустота тут честна: адрес назван источником минуту назад, и обрыв на нём - это
        именно «этой картинки сейчас нет», а не «спрашивать было нечего». Отличать 429
        от обрыва зовущему всё равно нечем, а вот приговор о СТАТЬЕ исключение
        по-прежнему оставляет: он-то и решает, давать ли имя картинке.
        """
        try:
            return self.files.fetch(address, timeout) if address else None
        except Exception:
            return None
