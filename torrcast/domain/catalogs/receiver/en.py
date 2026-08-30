"""Английские надписи кластера приёмника."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера приёмника.

    Английский - и умолчание продукта, и запасной каталог: ключа, которого тут нет,
    не существует вовсе, и :func:`torrcast.domain.catalogs.phrase.phrase` на нём падает
    громко, а не отвечает пустотой.
    """
    return {
        # Профили приёмников: подпись профиля, а не его ключ.
        "receiver.profile_cautious": "cautious (Samsung Q70D)",
        "receiver.profile_android_tv": "Android TV box (Xiaomi TV Stick)",
        "receiver.unnamed": "receiver",
        # Откуда взялся порог: конфиг, профиль или умолчание.
        "receiver.source_config": "written in the config",
        "receiver.source_config_default": "config default",
        "receiver.source_config_as_cautious": (
            "written in the config, but equal to the cautious one - profile {profile}"
        ),
        "receiver.source_profile": "profile {profile}",
        # Приёмка потока приёмником-заглушкой.
        "receiver.reception": (
            "segments {segments} · manifest {duration} s · decoded {decoded} s"
            " · gaps {gaps} · no CORS {no_cors} · peak {peak} Mbit/s"
        ),
        # Почему сеть не ответила.
        "receiver.why_shut": "the port is shut or the service is not running",
        "receiver.why_no_answer": "no answer to the connection",
        "receiver.why_timeout": "waited for an answer and never got one",
    }
