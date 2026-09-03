"""Тип картинки по её первым байтам; зовут полка постеров и маршрут серва."""

from __future__ import annotations

from typing import Final

#: Подпись формата в начале файла и тип, которым его называют по HTTP. Читается именно
#: подпись, а не расширение адреса: у Wikimedia уменьшенная копия вектора приезжает
#: растром, и ``.svg`` в имени файла к её содержимому отношения уже не имеет.
_SIGNS: Final = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
    (b"RIFF", "image/webp"),
)
#: Чем отвечаем на незнакомую подпись. Не пустотой: тело у нас на руках, и молчать о
#: типе значит заставить читателя гадать - а гадает он хуже, чем «поток байт».
UNKNOWN_TYPE: Final = "application/octet-stream"


def picture_type(body: bytes) -> str:
    """Тип картинки по подписи формата; подпись незнакома - :data:`UNKNOWN_TYPE`."""
    for sign, named in _SIGNS:
        if body.startswith(sign):
            return named
    return UNKNOWN_TYPE
