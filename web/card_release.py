"""Ключ раздачи карточки: таблица серий главнее фонового меню дорожек."""

from __future__ import annotations

from torrcast.domain.info_hash import info_hash
from torrcast.domain.release import Release
from web.heard import Heard


def card_release(episodes: Release | None, heard: Heard | None) -> str | None:
    """Вернуть hash раздачи файлов серии либо, у фильма, раздачи дорожек."""
    return info_hash(episodes) if episodes else (heard.release if heard else None)


__all__ = ["card_release"]
