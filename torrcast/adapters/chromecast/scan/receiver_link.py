"""Аптайм приёмника и то, чем он подключён к сети, - одним обычным запросом.

Спрашивает их проба самопроверки про ТВ."""

from __future__ import annotations

from typing import Final

import requests

#: Порт страницы сведений устройства. Не порт показа (:data:`~torrcast.adapters.chromecast.
#: scan.alive.CAST_PORT`): тот отвечает рукопожатием, а этот - обычным HTTP.
SETUP_PORT: Final = 8008
#: Страница сведений: аптайм и связь лежат прямо в ней, отдельного вопроса не нужно.
_INFO: Final = "/setup/eureka_info"


def receiver_link(address: str, timeout: float) -> tuple[float, bool | None]:
    """Сколько приёмник не перезагружался (секунды) и подключён ли он кабелем.

    Один обычный HTTP-запрос к странице сведений устройства: ни соединения показа, ни
    ``LOAD``, ни пультовых команд - приёмник этим не будится и чужой показ не трогается.

    Аптайм нулевой - устройство его не назвало. Кабель: ``True`` - да, ``False`` -
    Wi-Fi, ``None`` - не сказал.
    """
    try:
        payload = requests.get(f"http://{address}:{SETUP_PORT}{_INFO}", timeout=timeout).json()
    except (requests.RequestException, ValueError):
        return 0.0, None
    if not isinstance(payload, dict):
        return 0.0, None
    uptime, wired = payload.get("uptime"), payload.get("ethernet_connected")
    seconds = (
        float(uptime) if isinstance(uptime, int | float) and not isinstance(uptime, bool) else 0.0
    )
    return seconds, wired if isinstance(wired, bool) else None
