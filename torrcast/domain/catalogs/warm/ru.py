"""Русский каталог кластера прогрева."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера прогрева."""
    return {
        "warm.progress_head": "прогрето {warmed} из {duration}",
        "warm.done_note": "{head} - фильм целиком на диске, интернет больше не нужен",
        "warm.next_note": "{done}; следующая: {next}",
        "warm.trouble_note": "{head} - прогрев встал: {trouble}",
        "warm.warming_on": "{head} - грею дальше",
        "warm.busy_rival": "уступил перекоду",
        "warm.waiting_slot": "жду запаса показа",
        "warm.warming_why": "{head} - грею дальше ({why})",
        "warm.budget_exhausted": "бюджет диска {budget} ГБ исчерпан",
        "warm.floor_reached": "на разделе свободно {free} ГБ - это последний запас",
        "warm.fit": "годен",
        "warm.skew": "мимо сетки",
        "warm.blind": "не сверен",
        "warm.skew_where": "v{slot} на {minute}-й минуте лёг мимо сетки ({diff} с)",
        "warm.skew_hole": "{where} - это место осталось непрогретым",
        "warm.skew_retry": "{where} - перекладываю его заново",
        "warm.blind_why_timecode": "таймкод не прочитан",
        "warm.blind_why_not_movie": "лента прогона, а не фильма",
        "warm.blind_note": "сетку прогрева сверять нечем ({why}) - сторож укладки тут слеп",
    }
