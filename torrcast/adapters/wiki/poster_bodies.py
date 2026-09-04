"""Байты постеров по уже вынесенному приговору; общее у всех источников картинок.

Шаг этот у любого источника один и тот же: приговор назвал ГОТОВЫЕ адреса, и остаётся
их скачать. Разделено с приговором потому, что ждать байты на месте нельзя - десяток
картинок из сети стоил бы человеку секунд перед пустым экраном.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Final

from torrcast.domain.facts.ask import Ask
from torrcast.ports.bytes_client import BytesClient

#: Сколько картинок качается разом. Сами байты - самый долгий шаг из всех: запросов на
#: список уходит полдесятка, а картинок десяток, и подряд они складывались бы в секунды.
_LANES: Final = 4


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
