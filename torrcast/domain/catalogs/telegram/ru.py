"""Русские надписи Telegram-пульта показа."""


def ru() -> dict[str, str]:
    """Вернуть русские надписи Telegram-пульта."""
    return {
        "telegram.nothing_playing": "Показа нет.",
        "telegram.observer_refused": "Telegram отказал пульту показа: {detail}",
        "telegram.observer_recovered": "Telegram снова принимает пульт показа.",
    }
