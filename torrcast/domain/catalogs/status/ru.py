"""Русские надписи кластера ``cast status``."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера ``cast status``."""
    return {
        "status.warmed": "   прогрето {warm} из {duration}",
        "status.warmed_whole": " - весь фильм на диске, интернет не нужен",
        "status.file_info": (
            "   {ident} · файл #{file} · дорожка {track} · раздача {addr}, приёмник {receiver}"
        ),
        "status.no_frame": "картинки не было ни кадра",
        "status.at": "на {pos}",
        "status.torn": "показ оборвался: {what} - {was} ({reason})",
        "status.nothing_playing": "ничего не играет",
        "status.last_resumable": "последнее: «{title}» на {pos} / {duration}",
        "status.playing": "играю {what} - {pos} / {duration}",
        "status.dark": "показ погас: {what} - {pos} / {duration}",
        "status.dark_wait": "   {darkness} ({reason}) - жду возврата, подниму сам",
        "status.darkness_for": "темнота {hms}",
        "status.darkness": "темнота",
    }
