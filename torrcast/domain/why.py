"""Объясняет инфраструктурную ошибку короткой строкой."""

from typing import Final

from torrcast.domain.catalogs.phrase import phrase

#: Имя класса исключения - ключ каталога. Ключи, а не готовые слова: строка уезжает
#: человеку и обязана говорить на его языке (:mod:`torrcast.domain.catalogs.receiver`),
#: а имя класса приходит от чужой библиотеки и переводу не подлежит.
_REASONS: Final = {
    "ConnectionError": "receiver.why_shut",
    "ConnectTimeout": "receiver.why_no_answer",
    "ReadTimeout": "receiver.why_timeout",
    "Timeout": "receiver.why_timeout",
}


def why(exc: BaseException) -> str:
    """Короткая причина сетевой ошибки для сообщения пользователю."""
    for cls in type(exc).__mro__:
        if cls.__name__ in _REASONS:
            return phrase(_REASONS[cls.__name__])
    text = str(exc).split("\n")[0].split(" for url")[0]
    return text[:100] or type(exc).__name__
