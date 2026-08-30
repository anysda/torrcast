"""Английские надписи кластера разбора коробки файла."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера разбора коробки файла.

    Английский - и умолчание продукта, и запасной каталог: ключа, которого тут нет,
    не существует вовсе, и :func:`torrcast.domain.catalogs.phrase.phrase` на нём падает
    громко, а не отвечает пустотой.
    """
    return {
        # Матрёшка: голова файла и индекс Cues.
        "frames.ebml_broken": "a broken EBML number",
        "frames.mkv_no_segment": "this is not mkv: there is no Segment element in the file head",
        "frames.mkv_no_cues": (
            "the file has no Cues index - there is nowhere to take the keyframe map from"
        ),
        "frames.mkv_seekhead_not_ebml": "the SeekHead position does not read as an EBML element",
        "frames.mkv_seekhead_not_cues": "the SeekHead position holds not Cues but {ident}",
        "frames.mkv_cues_empty": "the file has Cues, but there is not a point in them",
        "frames.mkv_cues_lie": (
            "the Cues index lies: the point {at} refers to something other than a keyframe"
            " - a map made of it would be a ghost"
        ),
        # Коробка mp4: боксы и таблицы сэмплов.
        "frames.mp4_no_moov": (
            "the mp4 has no moov box - there is nowhere to take the keyframe map from"
        ),
        "frames.mp4_no_video_trak": "the mp4 has no video track",
        "frames.mp4_no_stbl": "the mp4 has no tables of the video track (stbl)",
        "frames.mp4_no_mdhd": "the mp4 does not read the time scale of the track (mdhd)",
        "frames.mp4_no_stts": (
            "the mp4 has no stts table - there is nowhere to take the frame times from"
        ),
        "frames.mp4_no_keyframe": "the mp4 has not a single keyframe",
        "frames.mp4_map_empty": "the mp4 has tables, but no map came together out of them",
    }
