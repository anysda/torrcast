"""Русские надписи кластера поиска."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера поиска."""
    return {
        "discover.indexer_silent": "не ответил",
        "discover.indexer_banned": "недоступен",
        "discover.indexer_one_gone": "индексер {name} {why} - выдача может быть хуже",
        "discover.indexer_many_gone": (
            "индексеры выпали из каталога: {listed} - выдача может быть хуже"
        ),
        "discover.indexer_one_late": (
            "индексер {name} ещё в пути - выдача пока без него, он может доехать"
        ),
        "discover.indexer_many_late": (
            "индексеры ещё в пути: {listed} - выдача пока без них, они могут доехать"
        ),
        "discover.budget_gone": "{what} не делаю: поиск уже съел цель в {goal} с",
        "discover.budget_gone_anyway": (
            "{what} всё равно делаю в свои {seconds} с: поиск уже съел цель в {goal} с"
        ),
        "discover.franchise_more": " и другие",
        "discover.franchise_no_number": (
            "«{name}»: картин во франшизе {total}, номера {index} нет - есть: {have}{more}"
        ),
        "discover.nothing_found": "по запросу «{name}» ничего не нашлось",
        "discover.origin_would_be_blind": (
            "оригинал «{alt}» - по справке; без неё второго запроса не было бы"
        ),
        "discover.origin_instead_of_blind": (
            "оригинал «{alt}» - по справке; без неё искал бы «{blind}»"
        ),
        "discover.search_phase": "поиск «{query}»",
        "discover.relayout_note": "«{query}» - это «{swapped}» в русской раскладке",
        "discover.search_whole_label": "поиск «{query}» целиком",
        "discover.whole_number_note": "по «{name}» картины не нашлось - искал «{query}» целиком",
        "discover.second_budget_note": (
            "поиск уже съел цель в {goal} с - добор по «{name}» всё равно делаю: "
            "картину ищут оба её имени"
        ),
        "discover.kin_line": "в каталоге есть {names} - cast {command}",
        "discover.prowlarr_not_configured": (
            "не настроен Prowlarr: apikey пуст, перезапусти ./install.sh"
        ),
        "discover.season_not_part": (
            "«{name}» - это сериал: номер {index} читаю сезоном, а не частью"
        ),
        "discover.nothing_parsed": "по запросу «{name}» ничего не разобралось",
        "discover.catalog_alias": "«{name}» - в каталоге это «{other}»",
        "discover.glued_pictures": "«{also}» и «{title}» - одна картина, раздач {count}",
        "discover.no_season_releases": "«{title}»: раздач с сезоном {season} нет",
        "discover.swarm_counts": "раздач в выдаче {total}, потрогали {touched}",
        "discover.swarm_later": (
            "назови картину иначе или зайди позже - другой запрос соберёт другую выдачу, "
            "а рой может ожить"
        ),
        "discover.swarm_no_peers": (
            "{counts} - пиров нет ни у одной, показывать нечего: {later} ({shown})"
        ),
        "discover.swarm_out_of_time": (
            "{counts} из очереди {queue_len} - эти молчат, на остальных не хватило "
            "времени (у потроганных числилось до {peers} сид), показывать нечего: "
            "{later} ({shown})"
        ),
        "discover.swarm_seed_some": " (у потроганных числилось до {peers} сид)",
        "discover.swarm_seed_none": " (сидов у потроганных не числилось)",
        "discover.swarm_pick_other": "выбери другой релиз",
        "discover.swarm_pick_manual": "выбери руками",
        "discover.swarm_untouched_some": (
            "{counts} - эти молчат, до остальных отбор не дошёл{seed}: {move} - "
            "cast releases <запрос>, потом cast <запрос> --release N ({shown})"
        ),
        "discover.swarm_all_silent": (
            "{counts} (все) - ни одна не отозвалась, хотя сиды у них числятся "
            "(до {peers}), показывать нечего: {later} ({shown})"
        ),
        "discover.swarm_reason_no_episode": "нужной серии нет - {count}",
        "discover.swarm_reason_heavy": "тяжелее потолка - {count}",
        "discover.swarm_untouched_unfit": (
            "{counts} - эти молчат, а остальным играть нечего ({reasons}), "
            "показывать нечего: {later} ({shown})"
        ),
        "discover.unfit_none_fit": (
            "годного релиза нет: раздач в выдаче {total}, и все до одной отсеял отбор ({why})"
        ),
        "discover.unfit_incomplete_tail": ", но выдача неполная - {late} ещё в пути",
        "discover.unfit_come_back": (
            "{line}: зайди позже - с полной выдачей годный рип может и найтись"
        ),
        "discover.unfit_final": (
            "{line} - картина есть, а раздачи её негодны: назови её иначе или зайди позже - "
            "другой запрос соберёт другую выдачу, а годный рип может появиться"
        ),
        "discover.gate_other_picture": (
            "по «{name}» справка нашла лишь похожее имя «{other}» - за чужой картиной не иду"
        ),
        "discover.retry_nothing": "добор по «{alt}» ничего не дал",
        "discover.retry_more_pictures": (
            "добор по «{alt}» привёз больше картин: {now} вместо "
            "{before} - остаюсь на выдаче по «{name}»"
        ),
        "discover.retry_no_new_releases": "добор по «{alt}» новых раздач картины не дал",
        "discover.retry_other_picture": (
            "по «{alt}» приехала другая картина - остаюсь на выдаче по «{name}»"
        ),
        "discover.retry_unconfirmed_name": ("имя «{alt}» взято со справки, сверить было не с чем"),
        "discover.retry_gain": "по-русски раздач {was} - добрал по «{alt}»: стало {now}",
        "discover.season_gap": (
            "«{title}» ({year}): раздач {count}, но сезона {season} среди них нет - "
            "названы {seasons}"
        ),
    }
