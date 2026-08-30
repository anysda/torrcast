"""Разбор HTTP, SOCKS и несовместимых MTProto-прокси."""

from __future__ import annotations

from urllib.parse import urlparse


def proxy(value: str) -> tuple[str | None, str | None]:
    """Вернуть нормализованный прокси и ключ диагноза либо два пустых ответа."""
    candidate = value.strip()
    lowered = candidate.lower()
    if lowered.startswith("tg://proxy?") or lowered.startswith("https://t.me/proxy?"):
        return None, "mtproto"
    try:
        parsed = urlparse(candidate)
        valid_port = parsed.port is not None
    except ValueError:
        valid_port = False
        parsed = urlparse("")
    if parsed.scheme not in {"http", "https", "socks5", "socks5h"}:
        return None, "invalid_proxy"
    if not parsed.hostname or not valid_port:
        return None, "invalid_proxy"
    return candidate, None
