"""Русские надписи кластера самопроверки."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера самопроверки.

    Ключа, которого тут нет, продукт скажет по-английски
    (:func:`torrcast.domain.catalogs.phrase.phrase`): русский каталог - надстройка над
    английским, а не второй полный словарь, который обязан поспевать за первым.
    """
    return {
        "health.ok": "ок      {text}",
        "health.warn": "внимание {text}",
        "health.bad": "плохо   {text}",
        "health.gib": "{size} ГиБ",
        "health.server_silent": "TorrServer не отвечает ({url}) - раздачи не будет",
        "health.cache_unreadable": "настройки TorrServer не читаются - размер кэша неизвестен",
        "health.cache_in_memory": (
            "кэш раздачи {size} в памяти, под показом это ~{weight} памяти из {total} машины"
        ),
        "health.cache_no_room": "{text} - не влезает: показ уронит машину, переставь install.sh",
        "health.cache_on_disk": "кэш раздачи {size} на диске ({path})",
        "health.cache_path_unset": "путь не задан",
        "health.cache_path_loose": (
            "{text} - служба положит его куда сама решит, переставь install.sh"
        ),
        "health.cache_free_unknown": "{text}, свободное место на разделе не читается",
        "health.cache_disk_room": "{text}, память службы ~{memory}, на разделе {free}",
        "health.cache_no_warm_room": "{text} - прогреву места не остаётся, обрыв оборвёт показ",
        "health.no_terminal": "терминала нет (запуск не интерактивный) - вопросы возьмут дефолты",
        "health.terminal_mode_unknown": (
            "терминал есть, но режим ввода не читается - кириллица не проверена"
        ),
        "health.iutf8_on": "уже включён",
        "health.iutf8_off": "выключен, включаем сами на время команды",
        "health.terminal_ok": "терминал: pty есть, IUTF8 {how} - кириллица в вопросах работает",
        "health.locale_ok": "локаль: {encoding} {env}",
        "health.locale_bad": "локаль {encoding} не UTF-8 - русские названия побьются ({env})",
        "health.locale_empty": "пусто",
        "health.no_ffmpeg": "ffmpeg не запускается - упаковывать поток нечем",
        "health.ffmpeg_no_burst": "{head}: -readrate_initial_burst инертен - старт будет медленным",
        "health.ffmpeg_pace_from_start": (
            "{head}: темп считается от начала файла, а не от места входа - перемотка повиснет"
        ),
        "health.ffmpeg_ok": "{head}, burst соблюдён, темп считается от места входа",
        "health.prowlarr_unit_unknown": (
            "службой Prowlarr не управляем - какой дорогой он идёт к трекерам, не видно"
        ),
        "health.prowlarr_ipv4": (
            "Prowlarr ходит к трекерам по IPv4 - по IPv6 их ответы обрываются раньше"
        ),
        "health.prowlarr_ipv6": (
            "Prowlarr может пойти к трекеру по IPv6, а по нему ответы обрываются раньше - "
            "индексер замолчит, и выглядеть это будет как пустой поиск; лечится строкой "
            "«{knob}» в его юните (её ставит установка)"
        ),
        "health.prowlarr_no_apikey": (
            "Prowlarr: apikey пуст - искать нечем, перезапусти ./install.sh"
        ),
        "health.prowlarr_silent": "Prowlarr не отвечает ({url}) - поиска не будет",
        "health.prowlarr_no_indexers": "Prowlarr отвечает, но индексеров ноль ({url})",
        "health.prowlarr_indexers": "Prowlarr отвечает, индексеров {count} ({url})",
        "health.indexer_paused": "индексер {name} отключён Prowlarr до {till}",
        "health.indexer_answered": "индексер {name} ответил на живой поиск",
        "health.indexer_irrelevant": (
            "индексер {name} ответил мимо контрольного запроса - выдача ненадёжна"
        ),
        "health.indexer_silent": "индексер {name} не ответил на живой поиск - выдача неполная",
        "health.core_present": "{indexer} на месте - {gives} в каталоге есть",
        "health.core_absent": (
            "{indexer} не заведён или выключен - искать можно, но {misses} в выдаче "
            "будет заметно меньше; вернуть - ./install.sh"
        ),
        "health.core_gives_west": "западные релизы и аниме",
        "health.core_misses_west": "западных релизов и аниме",
        "health.core_gives_russian": "русские раздачи и озвучки",
        "health.core_misses_russian": "русских раздач и озвучек",
        "health.tv_unnamed": (
            "адрес ТВ не задан: cast --tv (найдёт приёмники сам) или cast --tv <ip>"
        ),
        "health.tv_mock": "приёмник mock ({tv}) - каста наружу нет, это режим проверки",
        "health.tv_no_route": "до ТВ {tv} нет маршрута - каст не уйдёт",
        "health.tv_route": "ТВ {tv} виден с нашей ноги {ours}",
        "health.tv_port_shut": "порт {port} на ТВ не открылся ({error}) - ТВ обесточен?",
        "health.tv_port_open": "порт {port} на ТВ открыт - приёмник примет показ",
        "health.tv_no_info": "приёмник сведений о себе не отдал - аптайм и связь неизвестны",
        "health.link_wired": "по кабелю",
        "health.link_wifi": "по Wi-Fi",
        "health.link_unnamed": "связь не названа",
        "health.tv_link": "приёмник подключён {link}",
        "health.tv_uptime": "приёмник на ногах {uptime}, подключён {link}",
        "health.mdns_heard": "mDNS: услышал приёмников {count} ({names}) - имена в поиске будут",
        "health.tv_profile": "профиль приёмника: {title} - {how}",
        "health.tv_profile_by_hand": "{text}; назвать руками - ключ receiver_profile в конфиге",
        "health.hls_no_base": "адрес раздачи не собирается: {error}",
        "health.hls_plain": "раздача {base} - ни серта, ни DNS в пути показа",
        "health.hls_cert_unreadable": "раздача {base}, но серт {cert} не читается",
        "health.hls_cert_expiring": (
            "раздача {base}, серту осталось {days} дн - показ вот-вот отвалится"
        ),
        "health.hls_cert_ok": "раздача {base}, серту осталось {days} дн",
        "health.shelves": (
            "кэши в {shelf}: карт {keys}/{keys_kept} ({keys_mb} МБ), "
            "паспортов {probe}/{probe_kept} ({probe_mb} МБ)"
        ),
        "health.ago_minutes": "{count} мин",
        "health.ago_hours": "{count} ч",
        "health.ago_days": "{count} дн",
        "health.trace_missing": "следа нет в {directory} - `cast log` покажет пустоту",
        "health.trace_size": "{size} МБ",
        "health.trace_stale": "след есть ({size}), но последняя запись {days} дн назад",
        "health.trace_ok": "след {size}, последняя запись {ago} назад",
    }
