"""Язык отдельного файла звука, названный его каталогом: «Sound/Rus [Dub+MVO]/…mka»."""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.folder_language import folder_language
from torrcast.domain.media import Media

__all__ = ["voice_folder"]


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
    language = folder_language(path)
    if language is None:
        return media
    return replace(media, tracks=tuple(replace(t, language=language) for t in media.tracks))
