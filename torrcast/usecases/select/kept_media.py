"""Дорожки раздачи закладки по магниту её записи, мимо отбора."""

from __future__ import annotations

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.media import Media
from torrcast.usecases.select._voiced import _read_media, _Voiced


def kept_media(config: Config, entry: Entry) -> Media:
    """Дорожки раздачи закладки так, как их прочтёт продолжение с ``--voice``.

    Продолжение играет магнит записи мимо отбора (:func:`torrcast.usecases.select._voiced.
    _revoice`), поэтому ни выдача, ни ворота отбора не решают, чьи это дорожки. Поднятая
    раздача убирается на выходе (:meth:`torrcast.usecases.select._voiced._Voiced.drop`).
    """
    own = _Voiced()
    try:
        return _read_media(config, entry, own)
    finally:
        own.drop(config)


__all__ = ["kept_media"]
