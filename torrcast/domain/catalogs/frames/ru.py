"""Русские надписи кластера разбора коробки файла."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера разбора коробки файла.

    Ключа, которого тут нет, продукт скажет по-английски
    (:func:`torrcast.domain.catalogs.phrase.phrase`): русский каталог - надстройка над
    английским, а не второй полный словарь, который обязан поспевать за первым.
    """
    return {
        # Матрёшка: голова файла и индекс Cues.
        "frames.ebml_broken": "битое число EBML",
        "frames.mkv_no_segment": "это не mkv: элемента Segment в голове файла нет",
        "frames.mkv_no_cues": "в файле нет индекса Cues - карту опорных кадров взять неоткуда",
        "frames.mkv_seekhead_not_ebml": "по позиции из SeekHead читается не элемент EBML",
        "frames.mkv_seekhead_not_cues": "по позиции из SeekHead лежит не Cues, а {ident}",
        "frames.mkv_cues_empty": "Cues в файле есть, но точек в нём нет",
        "frames.mkv_cues_lie": (
            "индекс Cues врёт: точка {at} ссылается не на опорный кадр -"
            " карта из него была бы призрачной"
        ),
        # Коробка mp4: боксы и таблицы сэмплов.
        "frames.mp4_no_moov": "в mp4 нет бокса moov - карту опорных кадров взять неоткуда",
        "frames.mp4_no_video_trak": "в mp4 нет дорожки видео",
        "frames.mp4_no_stbl": "в mp4 нет таблиц дорожки видео (stbl)",
        "frames.mp4_no_mdhd": "в mp4 не читается масштаб времени дорожки (mdhd)",
        "frames.mp4_no_stts": "в mp4 нет таблицы stts - времена кадров взять неоткуда",
        "frames.mp4_no_keyframe": "в mp4 нет ни одного опорного кадра",
        "frames.mp4_map_empty": "таблицы mp4 есть, но карта из них не собралась",
    }
