"""Русские надписи кластера стенда отбора."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера стенда отбора."""
    return {
        "select_bench.phase_metadata_dht": "метаданные (DHT)",
        "select_bench.phase_done": "готово",
        "select_bench.phase_failed": "сбой",
        "select_bench.phase_missed_budget": "фаза «{phase}» не уложилась в бюджет",
        "select_bench.voice_search_phase": "ищу русскую озвучку: релиз {number} из {total} - ",
        "select_bench.honest_phase": "релиз {chosen} {look} - смотрю {number}",
        "select_bench.reason_no_answer": "не успел ответить",
        "select_bench.honest_no_answer_note": (
            "релиз {number} не успел ответить - играю {chosen} ({look})"
        ),
        "select_bench.unfit_note": "релиз {number} не годится ({why})",
        "select_bench.reason_no_russian_voice": "без русской озвучки",
        "select_bench.honest_no_voice_note": "релиз {number} не лучше (без русской озвучки)",
        "select_bench.reason_not_better": "не лучше ({quality})",
        "select_bench.honest_not_better_note": "релиз {number} не лучше ({quality})",
        "select_bench.honest_taken_note": (
            "релиз {chosen} {short} - беру {number} (настоящий {quality})"
        ),
        "select_bench.honest_kept_note": (
            "релиз {chosen} {short} - честнее рядом нет, играю его"
        ),
        "select_bench.reason_thin_swarm": (
            "рой везёт {got} из нужных {need} Мбит/с ({ratio}x)"
        ),
        "select_bench.tail_take": " - беру {following}",
        "select_bench.voiceless_head": "релиз {number} без русской озвучки ({lang})",
        "select_bench.no_swarm_capacity": (
            "ни один проверенный рой не тянет - беру лучший, релиз {number} ({ratio}x)"
        ),
        "select_bench.too_heavy_for_receiver": "слишком тяжёлый для приёмника",
        "select_bench.recode_beyond_machine": "перекод такого кадра этой машине не по силам",
        "select_bench.heavy_reason": "{reason}, ~{peak} Мбит/с",
        "select_bench.frame_needs_recode": (
            "{quality} - такой кадр приёмнику только через перекод"
        ),
        "select_bench.mute_fallback_note": (
            "русской озвучки нет ни в одной из проверенных раздач ({tried}) - "
            "включаю релиз {number}, звук {lang}"
        ),
        "select_bench.skipped_note": (
            "серии {want} нет в раздачах: {count} («{name}»...) - беру ту, где она есть"
        ),
        "select_bench.supply_note": (
            "рой релиза {number} везёт {got} при нужных {need} Мбит/с - беру ({ratio}x)"
        ),
        "select_bench.recheck_note": (
            "промолчала вся очередь ({total}) - спрашиваю релиз {number} ещё раз, одного и "
            "без отсрочек (жду до {budget} с)"
        ),
        "select_bench.recheck_result_alone_silent": "молчит и в одиночку",
        "select_bench.recheck_result_alone_unfit": "ответил в одиночку, но не годится",
        "select_bench.recheck_result_note": "релиз {number} {result} ({trouble})",
        "select_bench.recheck_no_voice_note": (
            "релиз {number} ответил в одиночку, но без русской озвучки"
        ),
        "select_bench.refusal_none_fit": "годного релиза нет ({shown}{more})",
        "select_bench.refusal_no_voice": (
            "русской озвучки нет ни в одной из проверенных раздач ({count})"
        ),
        "select_bench.more_tried": " и ещё {count}",
        "select_bench.refusal_rename_hint": (
            "{refused}: назови картину иначе - другой запрос соберёт другую выдачу"
        ),
        "select_bench.refusal_move_note": (
            "{refused}: {move} - cast releases <запрос>, потом cast <запрос> --release N"
        ),
    }
