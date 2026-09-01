"""Английские надписи кластера закладки показа."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера закладки показа."""
    return {
        "bookmark.release_word": "release",
        "bookmark.file_word": "file",
        "bookmark.named_from_start": (
            "“{title}” - {named} named by hand, playing the chosen one from the start; "
            "not raising the saved pick"
        ),
        "bookmark.release_named_resume": (
            "“{title}” - release named by hand, playing from the start; "
            "not raising the saved place {pos}"
        ),
        "bookmark.picked_in_menu": (
            "“{title}” - picture picked from the menu, playing from the start; "
            "not raising the saved place {pos}"
        ),
    }
