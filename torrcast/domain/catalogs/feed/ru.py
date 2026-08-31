"""Русские надписи кластера живой раздачи."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера живой раздачи."""
    return {
        "feed.weight_mb": " ({mb} МБ)",
        "feed.shrinking": "v{slot} тяжелее потолка{weight} - ужимаю на месте до {mbit} Мбит/с",
        "feed.shrink_reason_none": "ужимать нечем",
        "feed.shrink_reason_forbidden": "ужать нельзя",
        "feed.shrink_reason_failed": "ужать не вышло",
        "feed.shrink_done_reason": "ужатие на месте окончено",
        "feed.skip_heavy": (
            "⚠️ v{slot} пропускаю: кусок тяжелее потолка{weight}, а {reason} - "
            "этого места в показе не будет"
        ),
        "feed.source_mute_reason": "источник молчит дольше {secs} с",
        "feed.source_unreadable": (
            "источник не читается ({why}) - иду с прогретого, жду возврата сети"
        ),
        "feed.input_torn": "вход оборвался на середине, фильм не кончился",
        "feed.pack_broke_off": "упаковка оборвалась ({why})",
        "feed.retrying": "{what} - начинаю заново, попытка {attempt}",
        "feed.restart_reason": "перезапуск с сегмента {slot}",
        "feed.pack_from": "упаковка с {start} с",
        "feed.catchup": " (докатка {drop} с)",
        "feed.warm_torn": (
            "прогретый v{slot} оборван (не хватает {missing} с) - переделываю живой упаковкой"
        ),
        "feed.warm_off_grid": (
            "прогретый v{slot} мимо сетки ({diff} с) - переделываю живой упаковкой"
        ),
        "feed.give_up": (
            "⚠️ v{slot} пропускаю: {circles} перепаковки подряд не дали этого куска - "
            "этого места в показе не будет"
        ),
        "feed.pending_too_big": (
            "несданных кусков {mb} МБ в памяти - упаковку гашу, подниму её по запросу приёмника"
        ),
        "feed.pending_reason": "несданного {mb} МБ в памяти",
        "feed.rest_warmed_reason": "весь остаток прогрет",
        "feed.show_over": "показ окончен",
    }
