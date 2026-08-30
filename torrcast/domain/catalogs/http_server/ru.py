"""Русские надписи кластера HLS-раздачи."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера ``http_server``."""
    return {
        "http_server.no_route_to_tv": "не вижу маршрута до ТВ {tv}",
        "http_server.address_unset": "(адрес не задан)",
        "http_server.cert_unreadable": "не читается серт {path}: {reason}",
        "http_server.port_unavailable": "порт {port} занят или недоступен: {reason}",
        "http_server.trace_request": "запрос {name}{span} · ждал {waited} с · {got}",
        "http_server.trace_sent": "отдал {name} · {size} МБ за {seconds} с · {rate} Мбит/с",
        "http_server.trace_megabytes": "{size} МБ",
    }
