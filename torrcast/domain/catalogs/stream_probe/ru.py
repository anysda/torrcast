"""Русский каталог кластера ``stream_probe``."""

from __future__ import annotations


def ru() -> dict[str, str]:
    return {
        "stream_probe.disc_image": (
            "в раздаче нет отдельного видеофайла (похоже на образ диска) - "
            "возьми другой релиз: cast <запрос> --release N"
        ),
        "stream_probe.swarm_silent": "рой молчит - за отсрочку не пришло ни байта потока",
        "stream_probe.service_down": "TorrServer не отвечает",
        "stream_probe.torrent_lost": "TorrServer потерял нашу раздачу",
        "stream_probe.no_trackers": "раздача осталась без трекеров - метаданных нет",
        "stream_probe.thin_swarm": (
            "рой привозит {got} Мбит/с при нужных {need} Мбит/с - снабжения не хватает ({ratio}x)"
        ),
    }
