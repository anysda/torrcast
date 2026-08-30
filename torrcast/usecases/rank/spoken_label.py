"""Подпись дорожки вслух; зовут меню озвучек и строку запуска.

:attr:`~torrcast.domain.audio_track.AudioTrack.label` - ключ памяти
(:attr:`torrcast.domain.entry.Entry.voice`), и трогать его нельзя ни на байт: старый
запомненный выбор попросту перестанет находиться (:meth:`~torrcast.domain.media.Media.
find_voice`). У слова две формы - хранимая (``label``, неподвижная) и произносимая
(здесь) - и печатать человеку положено вторую.

Заголовок дорожки внутри подписи - чужой текст (данные раздачи, «Дубляж (MovieDalen)»),
и его мы не переводим: человек обязан увидеть то же, что написано в раздаче. Переводу
подлежит ровно одно наше слово - запасная подпись без языка и заголовка
(:mod:`torrcast.usecases.rank.spoken_voice`).
"""

from __future__ import annotations

from torrcast.domain.audio_track import AudioTrack
from torrcast.usecases.rank.spoken_voice import spoken_voice


def spoken_label(track: AudioTrack) -> str:
    """Подпись дорожки для печати человеку: как :attr:`AudioTrack.label`, но запасная
    подпись без языка и заголовка звучит на языке продукта."""
    return spoken_voice(track.label)
