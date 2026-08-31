"""Русский каталог кластера счастливого пути показа."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера счастливого пути показа."""
    return {
        "cmd_play.voice_apart": ("русская озвучка лежит отдельным файлом «{base}» - беру её"),
        "cmd_play.resumed_from": " · с {pos}",
        "cmd_play.dry_no_cast": "(--dry) {about} · файл «{base}» - каста нет",
    }
