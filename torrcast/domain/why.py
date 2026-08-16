"""Объясняет инфраструктурную ошибку короткой строкой."""

_REASONS = {
    "ConnectionError": "порт закрыт или служба не запущена",
    "ConnectTimeout": "нет ответа на подключение",
    "ReadTimeout": "не дождался ответа",
    "Timeout": "не дождался ответа",
}


def why(exc: BaseException) -> str:
    """Короткая причина сетевой ошибки для сообщения пользователю."""
    for cls in type(exc).__mro__:
        if cls.__name__ in _REASONS:
            return _REASONS[cls.__name__]
    text = str(exc).split("\n")[0].split(" for url")[0]
    return text[:100] or type(exc).__name__
