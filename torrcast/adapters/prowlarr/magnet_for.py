"""Собирает magnet-ссылку раздачи из её хэша, имени и списка публичных трекеров."""

from __future__ import annotations

from typing import Final
from urllib.parse import quote

#: Открытые трекеры, которые мы дописываем в каждый magnet. У раздач RuTracker
#: из Knaben публичных ретрекеров нет, у RuTor нет ``tr=`` вообще - без этого
#: списка пиры искались бы только через DHT.
PUBLIC_TRACKERS: Final = (
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://opentracker.io:6969/announce",
)


def magnet_for(info_hash: str, title: str = "") -> str:
    """Собрать magnet из hash, имени и списка публичных трекеров.

    ``magnetUrl`` в выдаче Prowlarr - ссылка-прокси на сам Prowlarr, поэтому опора у нас
    одна: ``infoHash``, а magnet собирается тут. Пиры после этого ищутся тремя способами
    сразу - magnet, DHT и публичные ретрекеры (:data:`PUBLIC_TRACKERS`).
    """
    parts = [f"magnet:?xt=urn:btih:{info_hash.lower()}"]
    if title:
        parts.append(f"dn={quote(title)}")
    parts += [f"tr={quote(t, safe='')}" for t in PUBLIC_TRACKERS]
    return "&".join(parts)


__all__ = ["PUBLIC_TRACKERS", "magnet_for"]
