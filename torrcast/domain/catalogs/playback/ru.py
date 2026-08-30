"""Русские надписи кластера показа."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера показа."""
    return {
        "playback.session_tag": "[сеанс {id}]",
        "playback.dry_run_no_cast": "(--dry) {about} - каста нет",
        "playback.now_playing": "играю {about} - на ТВ   (старт {secs:.0f} с)",
        "playback.now_playing_tagged": "{tag} играю {about} - на ТВ   (старт {secs:.0f} с)",
        "playback.frame_too_big": (
            "{quality} - такой кадр приёмник берёт только ужатым, а перекодирование "
            "выключено: нужен релиз {limit}p или ниже"
        ),
        "playback.waiting_tv": "жду телевизор",
        "playback.packing": "упаковка",
        "playback.did_not_start": "показ не запустился: {why}",
        "playback.picture_undetected_but_playing": (
            "картинку не доказал за {secs:.0f} с, но показ идёт: {said}"
        ),
        "playback.did_not_start_timeout": "показ не начался за {secs:.0f} с - {said}",
        "playback.raising_myself": "{tag} {why} - поднимаю показ сам",
        "playback.watched_cleared_warm": "досмотрено - прогретое с диска убрал",
        "playback.no_picture_source_unreadable": (
            "картинки не было ни разу: источник не читается ({why})"
        ),
        "playback.source_unreadable_cut_short": (
            "источник не читается ({why}) - показ оборван, цифры выше"
        ),
        "playback.no_picture_receiver_refused": (
            "картинки не было ни разу: приёмник не взял показ - поднять не удалось"
        ),
        "playback.receiver_did_not_finish": "приёмник не досмотрел поток - цифры выше",
        "playback.file_number_missing": "видеофайлов в раздаче {total}, номера {number} нет",
        "playback.picking_largest_file": (
            "видеофайлов в раздаче {total} - играю крупнейший, его доля {share:.2f}"
        ),
        "recoder.profile_container": "профиль тяжести: контейнер {mbit:.1f} Мбит/с, ",
        "recoder.basis_estimate": "оценке",
        "recoder.basis_measurement": "замеру",
        "recoder.tv_weight": "на ТВ уедет {mbit:.1f} Мбит/с по {basis}",
        "recoder.no_track_weight": "веса видеодорожки в паспорте нет - поправку наберу по факту",
        "recoder.map_not_grid": " (карта не сетка, но вес по ней честный)",
        "recoder.flat_profile": (
            "профиль тяжести ровный: {mbit:.1f} Мбит/с на каждый кусок по {basis} - "
            "тяжёлое место в лицо не знаю, ужимаю по среднему"
        ),
        "recoder.no_profile": (
            "профиля тяжести нет: ни карты, ни веса дорожки в паспорте - тяжёлый кусок "
            "ужимаю по факту, когда он окажется на выкладке"
        ),
        "recoder.map_no_offsets": "карта без смещений - веса кусков по ней не построить",
        "playback.tonemap_no_headroom": (
            "⚠️ тонемап 4К включён: он съедает запас скорости перекода - упаковка "
            "идёт вровень с показом, запаса от подгрузов нет"
        ),
    }
