"""Отказ моста одним словом: его же увидит Home Assistant в теле ответа 409."""

from __future__ import annotations

#: Слова отказа пульта и показа: часть того же договора, что и тип, перевода им нет.
BUSY, NOTHING_PLAYING, NO_NEXT, NO_VOLUME = "busy", "nothing_playing", "no_next", "no_volume"
#: Показ идёт во вкладке (TC-1210): пультом (перемотка, пауза) она не управляется -
#: приёмник-вкладка нарочно не умеет ``seek``/``pause``/``resume``
#: (:class:`torrcast.adapters.browser.browser_receiver.BrowserReceiver`), и мост отказывает,
#: не посылая команду, которую всё равно некому взять.
NO_REMOTE = "no_remote"


class RefusedError(Exception):
    """Отказ моста; слово отказа - часть договора, а не текст для человека.

    Пульт и показ отвечают коротким английским словом (``busy``, ``nothing_playing``,
    ``no_next``, ``no_volume``) - у него нет перевода, каталог надписей ему не нужен.
    Поиск (:meth:`hass.bridge.Bridge.search`) отвечает СЛОВОМ ПРОДУКТА - готовой фразой
    отказа, которую сказал бы `search_circle`, - и её мост не сочиняет и не переводит.
    """

    def __init__(self, word: str) -> None:
        super().__init__(word)
        #: Слово отказа: короткий английский ключ пульта/показа или фраза продукта.
        self.word = word
