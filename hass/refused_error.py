"""Отказ моста одним словом: его же увидит Home Assistant в теле ответа 409."""

from __future__ import annotations


class RefusedError(Exception):
    """Отказ моста; слово отказа - часть договора, а не текст для человека.

    Читает его карточка плеера, а не зритель, поэтому слово английское и короткое, и в
    каталог надписей ему не нужно: перевода у ключа договора не бывает.
    """

    def __init__(self, word: str) -> None:
        super().__init__(word)
        #: Слово отказа: ``busy``, ``nothing_playing``, ``no_next`` или ``no_volume``.
        self.word = word
