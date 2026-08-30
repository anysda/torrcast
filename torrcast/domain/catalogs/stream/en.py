"""Английские надписи кластера картинки и звука."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера картинки и звука.

    Английский - и умолчание продукта, и запасной каталог: ключа, которого тут нет,
    не существует вовсе, и :func:`torrcast.domain.catalogs.phrase.phrase` на нём падает
    громко, а не отвечает пустотой.
    """
    return {
        "stream.codec_bits": "{codec} {depth} bit",
        "stream.shrink": ", {frame}p - playing it at {out}p",
        "stream.recode_heavy": (
            "video {codec} {mbit} Mbit/s - heavy for the receiver, recoding it whole{shrink}"
        ),
        "stream.recode_whole": "video {codec} - recoding it whole on the fly{shrink}",
        "stream.video_warning": (
            "warning: video {codec} - the receiver may not take it, and we do not recode"
        ),
        "stream.voice_swap": "voice {heard} instead of {studio}",
    }
