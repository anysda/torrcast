"""Русские надписи кластера командной строки."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера командной строки."""
    return {
        "cli.about": "torrcast - найти релиз и кастить его на ТВ без скачивания",
        "cli.help_query": "название, либо stop / status",
        "cli.help_tv": "настройка ТВ: без адреса - найти приёмники в сети и выбрать из списка",
        "cli.help_telegram": "открыть меню настройки Telegram-бота",
        "cli.help_ru": "перейти на русский и запомнить выбор",
        "cli.help_en": "перейти на английский и запомнить выбор",
        "cli.help_release": (
            "отладка: релиз N выбранной картины; номера - из cast releases с тем же запросом"
        ),
        "cli.help_pick": "картина N из меню, без вопроса",
        "cli.help_menu": "показать список картин и спросить, а не включать самому",
        "cli.help_file": "отладка: взять файл N раздачи",
        "cli.metavar_voice": "N|СТУДИЯ",
        "cli.help_voice": "озвучка: номер или студия - взять и запомнить, без значения - меню",
        "cli.help_new": "та же раздача, файл и дорожка с начала",
        "cli.help_dry": "весь резолв без каста",
        "cli.help_upgrade": "обновить torrcast до последнего релиза",
        "cli.metavar_since": "СРОК",
        "cli.help_since": "cast log: с какого момента (2d / 12h / 30m / ГГГГ-ММ-ДД)",
        "cli.stray_flag": "флаг {flag} тут не понят",
        "cli.terminated_by_sigterm": "команда прервана сигналом SIGTERM",
        "cli.terminated_by_keyboard": "команда прервана с клавиатуры",
    }
