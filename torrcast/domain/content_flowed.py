"""Чистое правило content_flowed: отдал ли рой хоть кусочек содержимого по счёту службы."""

from __future__ import annotations

from collections.abc import Mapping

from torrcast.domain.json_value import JsonValue

#: Счётчики содержимого, а не протокола: байты и блоки, которые служба сама заказала.
USEFUL = ("bytes_read_useful_data", "chunks_read_useful")


def content_flowed(status: Mapping[str, JsonValue]) -> bool:
    """Насчитала ли служба хоть один полезный байт содержимого от роя.

    Это ответ на тот же вопрос, что и первый байт ``/stream``, только раньше: поток отдаёт
    байт, когда кусок целиком скачан и проверен (у сезонного пака кусок - мегабайты), а
    служба считает полезные байты с первого же блока. На стенде разница 1.3-2.7 с, и
    живая запись платила её на каждом старте (TC-1420). ``bytes_read`` сюда не годится:
    в нём метаданные и служебные сообщения, а пир, который отвечает и не отдаёт, их шлёт.
    Нет счётчика - нет ответа ``True``: тогда решает байт потока.
    """
    for key in USEFUL:
        value = status.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return True
    return False
