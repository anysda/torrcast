"""Провод описателя: добыча .torrent по ссылке, ``stat`` из ``list`` и ``upload``."""

from __future__ import annotations

from typing import Final

#: Срок добычи .torrent по ссылке: медиана 2.0 с, худшая 4.5 с на RuTor через Prowlarr.
FETCH_TIMEOUT: Final = 10.0
#: Срок короткого обращения к службе раздач.
CALL_TIMEOUT: Final = 5.0
#: Больше описание не бывает: потолок от мусора вместо .torrent.
MAX_BYTES: Final = 8 * 1024 * 1024


class TorrentHttp:
    """HTTP описателя. Сессия не общая с ``TorrServer``: он ходит из своего потока."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def fetch(self, url: str) -> bytes | None:
        """Байты .torrent по ссылке; редирект, отказ, срок или не bencode - ``None``."""
        import requests

        try:
            with requests.get(
                url, timeout=FETCH_TIMEOUT, allow_redirects=False, stream=True
            ) as response:
                if response.status_code != 200:
                    return None
                data = response.raw.read(MAX_BYTES + 1, decode_content=True)
        except (requests.RequestException, OSError):
            return None
        return data if data[:1] == b"d" and len(data) <= MAX_BYTES else None

    def stat(self, torrent_hash: str) -> int | None:
        """``stat`` раздачи из ``list``: он, в отличие от ``get``, закрытую не поднимает."""
        import requests

        try:
            with requests.post(
                f"{self.base_url}/torrents", json={"action": "list"}, timeout=CALL_TIMEOUT
            ) as response:
                response.raise_for_status()
                payload = response.json()
        except (requests.RequestException, ValueError):
            return None
        for item in payload if isinstance(payload, list) else []:
            if isinstance(item, dict) and str(item.get("hash", "")).casefold() == torrent_hash:
                value = item.get("stat")
                return value if isinstance(value, int) else None
        return None

    def upload(self, torrent_hash: str, data: bytes) -> bool:
        """Подать описание без записи в базу службы (поля ``save`` нет)."""
        import requests

        files = {"file": (f"{torrent_hash}.torrent", data, "application/x-bittorrent")}
        try:
            with requests.post(
                f"{self.base_url}/torrent/upload", files=files, timeout=CALL_TIMEOUT
            ) as response:
                return response.status_code == 200
        except requests.RequestException:
            return False


__all__ = ["CALL_TIMEOUT", "FETCH_TIMEOUT", "MAX_BYTES", "TorrentHttp"]
