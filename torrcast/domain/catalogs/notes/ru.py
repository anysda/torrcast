"""Русский каталог кластера предстартовых заметок."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера предстартовых заметок."""
    return {
        "notes.bitrate_warn_recode": (
            "внимание: ~{mbit} Мбит/с - тяжёлые куски перекодирую на ходу"
        ),
        "notes.bitrate_warn_no_recode": (
            "внимание: ~{mbit} Мбит/с - ресивер на таком битрейте может встать"
        ),
        "notes.file_debug": "файл: {base} · {size} · {duration} · {video}",
    }
