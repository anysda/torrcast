"""Русский каталог кластера ``chromecast_talk``."""

from __future__ import annotations


def ru() -> dict[str, str]:
    return {
        "chromecast_talk.no_status": "нет статуса",
        "chromecast_talk.with_code": ", код {code}",
        "chromecast_talk.without_code": ", без кода",
        "chromecast_talk.tv_did_not_start": "ТВ {address} не начал показ: {reason}",
        "chromecast_talk.tv_rejected_cast": "ТВ {address} не принял каст: {reason}",
        "chromecast_talk.tv_no_reconnect_answer": (
            "ТВ {address} не отозвался на переподключение: {reason}"
        ),
        "chromecast_talk.no_tv_address": (
            "адрес ТВ не задан: cast --tv - найдёт телевизоры в сети"
        ),
        "chromecast_talk.receiver_stuck": (
            "приёмник залип - закрываю приложение и соединение, гружу заново"
        ),
        "chromecast_talk.load_not_taken": ("LOAD не взяли ({reason}) - повтор {tries} из {limit}"),
        "chromecast_talk.receiver_dropped": (
            "приёмник отвалился на {position} с{reason} - повтор LOAD"
        ),
        "chromecast_talk.dying_on_one_chunk": (
            "показ умирает на одном куске {count}-й раз - перешагиваю его, "
            "{gap} с фильма мимо ({start} с -> {end} с)"
        ),
        "chromecast_talk.nudges_gave_no_frame": (
            "нуджи не дали ни кадра ({count} подряд) - прыгать перестаю, "
            "показ поднимется с последнего показанного кадра"
        ),
        "chromecast_talk.nudge_interrupted": "сторож перебил нуджем",
        "chromecast_talk.session_broke": "сессия оборвалась",
        "chromecast_talk.another_seek_arrived": "следом пришла ещё одна перемотка",
        "chromecast_talk.reconnect_timeout": (
            "ТВ {address} переподключается дольше {timeout} с - {what} не ушёл: {reason}"
        ),
        "chromecast_talk.reconnect_wait": (
            "сокет приёмника переподключается - {what} жду до {timeout} с"
        ),
        "chromecast_talk.stalled_skip": (
            "приёмник зависал - показ перешагнул {gap} с фильма ({start} с -> {end} с)"
        ),
        "chromecast_talk.refused_busy": "нельзя: приёмник занят чужим показом",
        "chromecast_talk.refused_crashed": "упал: {reason}",
        "chromecast_talk.refused_not_taken": "не взял: LOAD ушёл, а картинки не было",
        "chromecast_talk.refused_decoder_died": "не взял: декодер лёг, не начав показ",
        "chromecast_talk.refused_no_show_set": "нельзя: показ сюда не заводили",
        "chromecast_talk.refused_sulking": ("нельзя: приёмник помнит 404 и LOAD не берёт"),
        "chromecast_talk.manifest_not_fetched": "приёмник не забрал манифест: {reason}",
        "chromecast_talk.cors_header_missing": (
            "в ответе нет {header}: * - Chromecast такое молча не играет"
        ),
    }
