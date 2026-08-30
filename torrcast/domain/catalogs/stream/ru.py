"""Русские надписи кластера картинки и звука."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера картинки и звука.

    Ключа, которого тут нет, продукт скажет по-английски
    (:func:`torrcast.domain.catalogs.phrase.phrase`): русский каталог - надстройка над
    английским, а не второй полный словарь, который обязан поспевать за первым.
    """
    return {
        "stream.codec_bits": "{codec} {depth} бит",
        "stream.shrink": ", {frame}p - играю в {out}p",
        "stream.recode_heavy": (
            "видео {codec} {mbit} Мбит/с - тяжело приёмнику, перекодирую целиком{shrink}"
        ),
        "stream.recode_whole": "видео {codec} - перекодирую на ходу целиком{shrink}",
        "stream.video_warning": (
            "внимание: видео {codec} - ресивер может не взять, а мы не перекодируем"
        ),
        "stream.voice_swap": "озвучка {heard} вместо {studio}",
    }
