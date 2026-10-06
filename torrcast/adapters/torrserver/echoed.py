"""Жива ли служба раздач вообще: отвечает ли она на ``/echo`` за короткий срок.

Подъём службы (:mod:`.engine_restart`) спрашивает это ДО того, как убить её: молчит и
``/echo`` - HTTP мёртв целиком, и показа, который можно было бы оборвать, нет.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import requests

PROBE_TIMEOUT: Final = 3.0


def echoed(session: requests.Session, base_url: str) -> bool:
    """Отвечает ли служба на ``/echo`` за :data:`PROBE_TIMEOUT`."""
    import requests

    try:
        with session.get(f"{base_url}/echo", timeout=PROBE_TIMEOUT) as response:
            response.raise_for_status()
    except requests.RequestException:
        return False
    return True


__all__ = ["PROBE_TIMEOUT", "echoed"]
