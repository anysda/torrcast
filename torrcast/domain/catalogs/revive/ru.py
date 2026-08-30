"""Русские надписи кластера подъёма погасшего показа."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера подъёма показа."""
    return {
        "revive.screen_dark": "показ погас на {pos}",
        "revive.no_frame_yet": "показа не было ни кадра (заводили с {pos})",
        "revive.will_raise": "{said} ({why}) - подниму сам, как вернётся сеть",
        "revive.give_up": (
            "показ поднять не удалось ({tries} попыт., темнота {dark:.0f} с) - "
            "гашу; cast продолжит с {pos}"
        ),
        "revive.receiver_silent": "приёмник отмолчался",
        "revive.network_back": "сеть вернулась",
        "revive.raising": "{came} - поднимаю показ с {pos} (попытка {tries})",
        "revive.raised": "показ поднят с {pos}",
        "revive.no_reason_given": "причина не названа",
        "revive.refused": "приёмник показ не взял ({why}) - жду ещё",
        "revive.picture_started": "{tag} картинка пошла с {pos}",
        "revive.trace_line": (
            "{tag} запас: показ {pos:.0f} · упаковано {packed:.0f} · впереди {ahead:.0f} с · "
            "{mb:.0f} МБ · расхождение с манифестом {drift:.3f} с · {state}"
        ),
        "revive.tries_so_far": "поднимал {tries} из {limit}",
        "revive.source_not_back": "источник не вернулся - приёмник не трогаю",
        "revive.dark_report": "{tag} темнота {dark} ({why}) - картинки нет; {spent}, погашу через {left}",
        "revive.no_network": "сети нет ({why}) - показ обеспечен до {until}",
        "revive.pause_from_remote": "пауза на пульте - упаковку гашу",
        "revive.pause_session_lost": (
            "сессию на паузе приёмник потерял - возвращаю показ на {pos}; "
            "сам он не начнётся"
        ),
        "revive.pause_restored": "показ вернул на {pos} и стоит на паузе - жду зрителя",
        "revive.receiver_dropped_show": "приёмник бросил показ",
        "revive.source_back_waiting": "источник вернулся - жду готовности потока",
        "revive.source_unreadable_wait": (
            "источник не читается ({why}) - жду его возврата, показ подниму сам"
        ),
        "revive.pack_broke": "упаковка оборвалась: {trouble}",
        "revive.fully_warm_switch_disk": (
            "прогрето целиком - живую упаковку гашу, показ идёт с диска"
        ),
        "revive.tail_ended": (
            "конец картины: указатель стоит на {pos} уже {secs:.0f} с - считаю доигранным"
        ),
        "revive.closed_by_remote": "{tag} показ закрыт с пульта на {pos} - поднимать не буду",
    }
