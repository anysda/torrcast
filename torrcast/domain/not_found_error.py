"""Ошибка NotFoundError; используется публичным API."""

from torrcast.domain.torrcast_error import TorrcastError


class NotFoundError(TorrcastError):
    """Ничего не нашли по запросу. Код выхода 1."""

    #: Ответил ли на этот поиск каждый спрошенный индексер. Только тогда «ничего» - правда
    #: о каталоге, а не о его выпавшей части (:mod:`torrcast.usecases.discover.circle_watch`).
    whole: bool = False
