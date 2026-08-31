"""Русский каталог кластера доборов каталога."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера доборов каталога."""
    return {
        "reinforce.year_mismatch": (
            "под этим именем в каталоге лежит картина {found_year} года, "
            "а не {about_year} - другой там нет"
        ),
        "reinforce.refine_reason": "уточнение по «{name}»",
        "reinforce.search_phase": "поиск «{name}»",
        "reinforce.year_unknown": "год не назван",
        "reinforce.ceiling_note": (
            "по «{name}» выдача упёрлась в потолок каталога, а самой картины в ней нет - "
            "добрал по «{refined}»: «{title}» ({year})"
        ),
        "reinforce.late_indexer": "опоздавший индексер",
        "reinforce.arrived_after_list": "«{who}» доехал после списка: ",
        "reinforce.foreign_brought": "привёз {names} - ",
        "reinforce.and_more": " и ещё {n}",
        "reinforce.not_listed_singular": "в списке её не было, в отбор она не пойдёт",
        "reinforce.not_listed_plural": "в списке их не было, в отбор они не пойдут",
        "reinforce.season_reason": "добор сезона {season}",
        "reinforce.season_note": "сезона {season} в выдаче не было - добрал по «{query}»",
        "reinforce.topup_counts": "раздач {now} вместо {was}",
        "reinforce.topup_changed": ", верх отбора другой",
        "reinforce.voice_reason": "добор по «{exact}»",
        "reinforce.voice_note": (
            "«{title}» по-русски есть только там, где играть нечем - "
            "добрал по «{exact}»: раздач стало {now}"
        ),
    }
