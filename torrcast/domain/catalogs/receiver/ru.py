"""Русские надписи кластера приёмника."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера приёмника.

    Ключа, которого тут нет, продукт скажет по-английски
    (:func:`torrcast.domain.catalogs.phrase.phrase`): русский каталог - надстройка над
    английским, а не второй полный словарь, который обязан поспевать за первым.
    """
    return {
        # Профили приёмников: подпись профиля, а не его ключ.
        "receiver.profile_cautious": "осторожный (Samsung Q70D)",
        "receiver.profile_android_tv": "приставка Android TV (Xiaomi TV Stick)",
        "receiver.unnamed": "приёмник",
        # Откуда взялся порог: конфиг, профиль или умолчание.
        "receiver.source_config": "написан в конфиге",
        "receiver.source_config_default": "умолчание конфига",
        "receiver.source_config_as_cautious": (
            "написан в конфиге, но равен осторожному - профиль {profile}"
        ),
        "receiver.source_profile": "профиль {profile}",
        # Приёмка потока приёмником-заглушкой.
        "receiver.reception": (
            "сегментов {segments} · манифест {duration} с · декодировано {decoded} с"
            " · разрывов {gaps} · без CORS {no_cors} · пик {peak} Мбит/с"
        ),
        # Почему сеть не ответила.
        "receiver.why_shut": "порт закрыт или служба не запущена",
        "receiver.why_no_answer": "нет ответа на подключение",
        "receiver.why_timeout": "не дождался ответа",
    }
