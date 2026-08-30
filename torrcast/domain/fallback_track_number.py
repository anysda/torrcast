"""Отличить нашу запасную подпись дорожки от чужого текста заголовка."""

from __future__ import annotations

from typing import Final

#: Запасная подпись, когда дорожка не назвала ни языка, ни заголовка
#: (:attr:`torrcast.domain.audio_track.AudioTrack.label`). Часть ключа памяти
#: (:attr:`torrcast.domain.entry.Entry.voice`) - и потому русская всегда, даже под
#: английским продуктом. Кто говорит её человеку - зовёт :func:`fallback_track_number`,
#: а не собирает тот же префикс заново (:mod:`torrcast.usecases.rank.spoken_voice`).
FALLBACK_PREFIX: Final = "дорожка "


def fallback_track_number(value: str) -> int | None:
    """Номер дорожки, если ``value`` - запасная подпись (:data:`FALLBACK_PREFIX`);
    иначе ``None`` - это чужой текст (заголовок дорожки из раздачи), и трогать его
    нельзя (:mod:`torrcast.usecases.rank.spoken_voice`)."""
    if not value.startswith(FALLBACK_PREFIX):
        return None
    tail = value[len(FALLBACK_PREFIX) :]
    return int(tail) if tail.isdigit() else None
