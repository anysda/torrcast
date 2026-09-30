"""Байты постеров по уже вынесенному приговору; общее у всех источников картинок.

Шаг этот у любого источника один и тот же: приговор назвал ГОТОВЫЕ адреса, и остаётся
их скачать. Разделено с приговором потому, что ждать байты на месте нельзя - десяток
картинок из сети стоил бы человеку секунд перед пустым экраном.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Final
from urllib.parse import urlsplit

from torrcast.domain.facts.ask import Ask
from torrcast.ports.bytes_client import BytesClient
from torrcast.ports.journal.slot import journal

#: Сколько картинок качается разом. Сами байты - самый долгий шаг из всех: запросов на
#: список уходит полдесятка, а картинок десяток, и подряд они складывались бы в секунды.
_LANES: Final = 4
#: Which share of its timeout a refusal has to take to read as a silent host, not a quick "no".
#: A 404 or a TLS alert comes back in milliseconds; a host that sat on the request for most of
#: its allowance will sit on the picture's next address too, and the spare waits behind it.
_STALLED: Final = 0.75


class PosterBodies:
    """Скачивает постеры пачкой по названным адресам."""

    def __init__(self, files: BytesClient) -> None:
        self.files = files

    def bodies(self, wanted: dict[Ask, list[str]], timeout: float) -> dict[Ask, bytes]:
        """Байты постеров по названным адресам; ни один не отдал байт - картины нет.

        Разбора тут нет вовсе: адреса назвал приговор. Адреса пробуются по порядку, а не
        один первый: приговор назвал их несколько именно затем, чтобы обрыв на одной
        картинке не оставлял плитку битой. Один и тот же адрес качается ОДИН раз - у
        сборника и его первой части постер общий.
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
        """Байты первого адреса, который их отдал; молчат все - ``None``.

        A host that stalled on one address is not asked for the picture's next one: IMDb names
        two files on the same host, and a cold dead host cost the tile twice its timeout before
        the other source's spare (:mod:`hass.spare_bodies`) got its turn.
        """
        stalled: set[str] = set()
        for address in addresses:
            if urlsplit(address).netloc in stalled:
                continue
            with guard:
                seen = address in loaded
                body = loaded.get(address)
            if not seen:
                began = time.monotonic()
                body = self._body(address, timeout)
                if not body and time.monotonic() - began >= _STALLED * timeout:
                    stalled.add(urlsplit(address).netloc)
                with guard:
                    loaded[address] = body
            if body:
                return body
        return None

    def _body(self, address: str, timeout: float) -> bytes | None:
        """Скачать один постер; сеть промолчала - пустота, а не исключение.

        Пустота тут честна: адрес назван источником минуту назад, и обрыв на нём - это
        именно «этой картинки сейчас нет», а не «спрашивать было нечего». Зовущему и
        правда нечем отличить 429 от обрыва, а вот приговор о СТАТЬЕ исключение
        по-прежнему оставляет: он-то и решает, давать ли имя картинке.

        🔴 Но пустота, отданная зовущему, и МОЛЧАНИЕ - разные вещи, и раньше тут было
        второе. Плитка обещала картинку и оставалась битой, а в журнале не было ни
        строки: проглоченное исключение стирало не шум, а единственный признак, по
        которому этот отказ вообще отличим от «постера у картины нет». Причина уходит
        в след - решение зовущего от этого не меняется ни на шаг.
        """
        try:
            return self.files.fetch(address, timeout) if address else None
        except Exception as refusal:
            journal().emit(
                "posters",
                "poster_body_missed",
                address=address,
                refusal=f"{type(refusal).__name__}: {refusal}",
                timeout=round(timeout, 1),
            )
            return None
