"""Отдала ли раздача хоть байт содержимого: читается в фоне с той секунды, как спросили."""

from __future__ import annotations

import threading
import urllib.request
from typing import TYPE_CHECKING

from torrcast.domain.warm_open import WARM_TIMEOUT

if TYPE_CHECKING:
    from collections.abc import Callable


def first_byte(source_url: str) -> Callable[[float], bool | None]:
    """Начать читать файл раздачи с нуля; ответ - ждалка «пришёл ли первый байт за срок».

    Ждалка отвечает ``True``, когда байт пришёл, ``False``, когда срок вышел, а байта нет,
    и ``None``, когда служба на запрос ответила отказом (ошибка, обрыв, пустой ответ) -
    это «спросить не удалось», а не приговор раздаче. Чтение начинается сразу, поэтому
    ожидание идёт внахлёст с тем, что зовущий делает до вопроса.

    Читается ровно один байт: подтвердить отдачу достаточно, а голову файла в кэш службы
    тянет уже показ - второй раз её брать незачем.
    """
    done = threading.Event()
    got: list[bool | None] = [None]

    def pull() -> None:
        request = urllib.request.Request(source_url, headers={"Range": "bytes=0-"})
        try:
            with urllib.request.urlopen(request, timeout=WARM_TIMEOUT) as answer:
                got[0] = True if answer.read(1) else None
        except Exception:  # любой отказ службы - «спросить не удалось»
            got[0] = None
        done.set()

    threading.Thread(target=pull, daemon=True).start()

    def arrived(timeout: float) -> bool | None:
        if not done.wait(max(timeout, 0.0)):
            return False
        return got[0]

    return arrived
