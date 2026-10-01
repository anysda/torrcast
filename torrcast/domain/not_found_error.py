"""Ошибка NotFoundError; используется публичным API."""

from torrcast.domain.torrcast_error import TorrcastError


class NotFoundError(TorrcastError):
    """Ничего не нашли по запросу. Код выхода 1."""

    #: Ответил ли на этот поиск каждый спрошенный индексер. Только тогда «ничего» - правда
    #: о каталоге, а не о его выпавшей части (:mod:`torrcast.usecases.discover.circle_watch`).
    whole: bool = False
    #: Who of the asked catalogue did not answer, and whom Prowlarr took out of reach: the
    #: names a cut empty circle owes the person instead of a bare «nothing».
    silent: tuple[str, ...] = ()
    banned: tuple[str, ...] = ()
    #: Who refused behind an empty page while the search ran: a refusal, not a silence.
    refused: tuple[str, ...] = ()
    #: Every release the selection touched stayed silent: the swarm said nothing about the
    #: picture, so the refusal is no verdict on it (:func:`web.voice_lookup.VoiceLookup.shelf_of`).
    swarm: bool = False
