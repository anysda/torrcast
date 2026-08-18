"""Дорожка по умолчанию идёт без метки языка; зовёт запуск показа."""

from __future__ import annotations

from torrcast.domain.media import Media


def default_unnamed(media: Media) -> bool:
    """Дорожка, которая заиграет по умолчанию, идёт БЕЗ метки языка.

    🔴 :meth:`~torrcast.domain.media.Media.default_track` возвращает ПОЛЕ ``index`` дорожки, а не
    её место в списке. Совпадают они ровно пока паспорт собран подряд самим ffprobe
    (:func:`torrcast.adapters.stream_probe.media_fields._track` нумерует ``enumerate`` по звуковым
    потокам), а паспорт, поднятый из кэша, приходит с теми номерами, какие в нём записаны. Поэтому
    место сверяется с длиной - тем же ходом, что и в :func:`heard`, - и промах стоит вежливого
    отката на верхнюю дорожку, а не ``IndexError`` посреди запуска показа.
    """
    if not media.tracks:
        return False
    index = media.default_track()
    track = media.tracks[index] if index < len(media.tracks) else media.tracks[0]
    return not track.named
