"""Справка «дорожка на языке зрителя в файле есть»; зовут гейт релиза и развилка звука."""

from __future__ import annotations

from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.media import Media


def sought_voice(media: Media, language: str = "") -> bool:
    """Паспорт ПРЯМО говорит, что дорожка на языке зрителя в файле есть.

    Язык зрителя - это язык продукта (:func:`~torrcast.domain.catalogs.tongue.tongue`):
    под английской ручкой искомый звук английский, под русской - русский. Ровно этот
    выбор ставит и ярус лестницы (:func:`torrcast.domain.voice_order._tier`), поэтому
    гейт, лестница и надписи ищут одно и то же - и зовут одним именем.
    """
    if (language or tongue()) == EN:
        return any(track.is_english for track in media.tracks)
    return media.russian
