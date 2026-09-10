"""Договорные слова о причине несостоявшегося подъёма показа.

Экран подготовки страницы (``web/static/player-screens.js``) умеет говорить отказ, но
ему нужна причина СЛОВОМ, а не строкой консоли: консольная строка пишется языком
продукта, а веб-кинотеатр - только по-английски (решение владельца 13 от 06-09-2026),
и свои надписи он берёт из каталога по ключу. Слова ниже - этот ключ и есть: их пишут
места, которые причину ЗНАЮТ (юнит показа и командная строка - разные процессы, слово
переезжает файлом, :mod:`torrcast.adapters.filesystem.state.file_refusal_record`), а читает
мост (:meth:`hass.bridge.Bridge.state`).

Перевода словам нет, как и словам отказа пульта (:mod:`hass.refused_error`): это часть
договора, а не текст для человека. Человеческий текст собирает страница из каталога
``web.player.refused_<слово>``; слова, которого в каталоге нет, она не сочиняет и
показывает короткую строку без причины.

🔴 Названо ровно то, что продукт различает КЛАССОМ, а не текстом строки: строка пишется
языком зрителя и правится, класс - нет. Так, :class:`~torrcast.domain.not_found_error.
NotFoundError` одним родом крывает и «ничего не нашлось», и «кадр не берётся», и «такой
озвучки нет» - назвать их одним словом значило бы соврать, и поэтому он тут отсутствует:
неразличимая причина остаётся короткой строкой «Could not start playback» без хвоста.
"""

from __future__ import annotations

from typing import Final

#: Приёмник не ответил на подъём: его нет в сети (первый коннект,
#: :meth:`torrcast.adapters.chromecast.cast.receiver_link._Link._no_link`) или он не взял
#: показ, и лестница воскрешения его не подняла
#: (:func:`torrcast.usecases.playback._show_blame._blame_the_end`).
RECEIVER_DID_NOT_ANSWER: Final = "receiver_did_not_answer"

#: Молчит служба раздач (:class:`torrcast.domain.server_down_error.ServerDownError`):
#: без неё не прочитать ни одного источника, и перебирать их незачем.
SOURCE_DID_NOT_ANSWER: Final = "source_did_not_answer"

#: Служба жива, а раздачу не прочитать (:func:`torrcast.usecases.playback._show_end.
#: _blame_the_end` при живой службе): метаданные или байты источника не пришли.
SOURCE_COULD_NOT_BE_READ: Final = "source_could_not_be_read"

__all__ = [
    "RECEIVER_DID_NOT_ANSWER",
    "SOURCE_COULD_NOT_BE_READ",
    "SOURCE_DID_NOT_ANSWER",
]
