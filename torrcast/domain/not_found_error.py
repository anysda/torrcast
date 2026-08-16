"""Ошибка NotFoundError; используется публичным API."""

from torrcast.domain.torrcast_error import TorrcastError


class NotFoundError(TorrcastError):
    """Ничего не нашли по запросу. Код выхода 1."""
