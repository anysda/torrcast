"""Язык, названный каталогом раскладки раздачи: «Sound/Rus [Dub+MVO]/…mka»."""

from __future__ import annotations

import re
from typing import Final

__all__ = ["folder_language"]

_FOLDER_LANGUAGES: Final = (
    (re.compile(r"^(?:rus(?:sian)?|рус(?:ск\w*)?)(?![a-zа-яё])", re.IGNORECASE), "rus"),
    (re.compile(r"^(?:eng(?:lish)?|англ\w*)(?![a-zа-яё])", re.IGNORECASE), "eng"),
    (re.compile(r"^(?:jap(?:anese)?|jpn|япон\w*)(?![a-zа-яё])", re.IGNORECASE), "jpn"),
)


def folder_language(path: str) -> str | None:
    """Язык, названный ближайшим к файлу каталогом раскладки; корень раздачи не судится."""
    folders = path.replace("\\", "/").split("/")[1:-1]
    for folder in reversed(folders):
        for pattern, language in _FOLDER_LANGUAGES:
            if pattern.match(folder.strip()):
                return language
    return None
