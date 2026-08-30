"""Русские надписи кластера кодировщика тяжёлых кусков."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера ``recode``."""
    return {
        "recode.no_heavy_pieces": "тяжёлых кусков нет - перекодировать нечего",
        "recode.and": "и",
        "recode.bitrate_from": "битрейт от {mbit} Мбит/с",
        "recode.piece_weight_above": "вес куска выше {mb} МБ",
        "recode.pieces_to_recode": (
            "кусков на перекод {count} из {total} ({share}% фильма, {marks}) - "
            "перекодирую заранее не выше {ceiling} Мбит/с"
        ),
        "recode.report": (
            "перекодировано {made} кусков ({seconds} с фильма), тяжёлых ушло как есть {late}"
        ),
        "recode.rewind": "перемотка",
        "recode.head_matters_more": "голова прогона важнее",
        "recode.packing_stuck": "упаковка встала на v{slot}",
        "recode.show_over": "показ окончен",
        "recode.run_over": "заход окончен",
        "recode.recoded_pieces": (
            "перекодировал v{first}...v{last} ({seconds} с фильма за {spent} с, {preset}, "
            "{rate}x - план {plan} от таблицы)"
        ),
        "recode.yielded_nothing": (
            "перекодирование v{first}...v{last} не дало ни куска за {spent} с"
        ),
    }
