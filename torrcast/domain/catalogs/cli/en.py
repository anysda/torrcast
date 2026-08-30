"""Английские надписи кластера командной строки."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера командной строки.

    Английский - и умолчание продукта, и запасной каталог: без него ``cast --help``
    показывал бы русский текст даже английской установке, потому что справка
    ``argparse`` строится один раз при разборе, а не по месту показа.
    """
    return {
        "cli.about": "torrcast - find a release and cast it to the TV without downloading",
        "cli.help_query": "the title, or stop / status",
        "cli.help_tv": (
            "TV setup: without an address - find receivers on the network and pick from the list"
        ),
        "cli.help_telegram": "open the Telegram bot setup menu",
        "cli.help_ru": "switch to Russian and remember the choice",
        "cli.help_en": "switch to English and remember the choice",
        "cli.help_release": (
            "debug: release N of the chosen picture; numbers come from cast releases "
            "with the same query"
        ),
        "cli.help_pick": "picture N from the menu, without asking",
        "cli.help_menu": "show the list of pictures and ask, instead of switching on by itself",
        "cli.help_file": "debug: take file N of the release",
        "cli.metavar_voice": "N|STUDIO",
        "cli.help_voice": "voice: number or studio - take and remember, no value - menu",
        "cli.help_new": "the same release, file and track from the start",
        "cli.help_dry": "the whole resolve without casting",
        "cli.metavar_since": "SPAN",
        "cli.help_since": "cast log: since when (2d / 12h / 30m / YYYY-MM-DD)",
        "cli.terminated_by_sigterm": "command interrupted by SIGTERM",
        "cli.terminated_by_keyboard": "command interrupted from the keyboard",
    }
