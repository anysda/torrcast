"""Язык отдельного файла звука, названный его каталогом: «Sound/Rus [Dub+MVO]/…mka»."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Final

from torrcast.domain.media import Media

__all__ = ["voice_folder"]

_FOLDER_LANGUAGES: Final = (
    (re.compile(r"^(?:rus(?:sian)?|рус(?:ск\w*)?)(?![a-zа-яё])", re.IGNORECASE), "rus"),
    (re.compile(r"^(?:eng(?:lish)?|англ\w*)(?![a-zа-яё])", re.IGNORECASE), "eng"),
    (re.compile(r"^(?:jap(?:anese)?|jpn|япон\w*)(?![a-zа-яё])", re.IGNORECASE), "jpn"),
)


def voice_folder(media: Media, path: str) -> Media:
    """Паспорт файла звука с языком из каталога, если сам файл язык не назвал.

    🔴 TC-1267. «Наруто (S1) [RUS(ext), ENG, JAP+Sub]»: русская дорожка лежит в
    «Sound/Rus [Dub+MVO]/», у самого .mka тега языка нет, и серия играла по-японски.
    Имя ФАЙЛА звука язык не называет (194 из 194), а каталог раскладки - называет.
    Корневой каталог раздачи не судится: там название картины («Russian Doll»).
    Язык, названный самим файлом, каталог не перебивает.
    """
    if not media.tracks or any(track.named for track in media.tracks):
        return media
    folders = path.replace("\\", "/").split("/")[1:-1]
    for folder in reversed(folders):
        for pattern, language in _FOLDER_LANGUAGES:
            if pattern.match(folder.strip()):
                tracks = tuple(replace(track, language=language) for track in media.tracks)
                return replace(media, tracks=tracks)
    return media
