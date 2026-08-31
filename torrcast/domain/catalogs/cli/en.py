"""Английские надписи кластера разбора argv."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера разбора argv.

    Английский - и умолчание продукта, и запасной каталог: без него ``cast --help``
    показывал бы русский текст даже английской установке, потому что справка
    ``argparse`` строится один раз при разборе, а не по месту показа.
    """
    return {
        "cli.about": "torrcast - find a release and cast it to the TV without downloading",
        "cli.query_help": "the title, or stop / status",
        "cli.tv_help": (
            "TV setup: without an address - find receivers on the network and pick from the list"
        ),
        "cli.telegram_help": "open the Telegram bot setup menu",
        "cli.ru_help": "switch to Russian and remember the choice",
        "cli.en_help": "switch to English and remember the choice",
        "cli.release_help": (
            "debug: release N of the chosen picture; numbers come from cast releases "
            "with the same query"
        ),
        "cli.pick_help": "picture N from the menu, without asking",
        "cli.menu_help": "show the list of pictures and ask, instead of switching on by itself",
        "cli.file_help": "debug: take file N of the release",
        "cli.voice_metavar": "N|STUDIO",
        "cli.voice_help": "voice: number or studio - take and remember, no value - menu",
        "cli.from_start_help": "the same release, file and track from the start",
        "cli.dry_help": "the whole resolve without casting",
        "cli.since_metavar": "SPAN",
        "cli.since_help": "cast log: since when (2d / 12h / 30m / YYYY-MM-DD)",
    }
