"""Русские надписи кластера закладки показа."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера закладки показа."""
    return {
        "bookmark.release_word": "релиз",
        "bookmark.file_word": "файл",
        "bookmark.named_from_start": (
            "«{title}» - {named} назван руками, играю выбранное с начала; "
            "сохранённый выбор не поднимаю"
        ),
        "bookmark.release_named_resume": (
            "«{title}» - релиз назван руками, играю с начала; "
            "сохранённое место {pos} не поднимаю"
        ),
        "bookmark.picked_in_menu": (
            "«{title}» - картина выбрана в меню, играю с начала; "
            "сохранённое место {pos} не поднимаю"
        ),
    }
