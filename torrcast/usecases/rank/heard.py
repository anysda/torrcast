"""Каким языком заговорит файл: язык дорожки, которую взял бы показ; зовут строки отбора."""

from __future__ import annotations

from torrcast.domain.media import Media
from torrcast.usecases.rank.spoken import spoken


def heard(media: Media) -> str:
    """Каким языком заговорит этот файл: язык дорожки, которую взял бы показ.

    Нужен строкам отбора (:meth:`Bench.resolve`): «релиз 1 без русской озвучки» само по
    себе не говорит человеку ничего о том, что он услышит, а «(японский)» говорит. Берётся
    та же дорожка, что и играла бы (:meth:`torrcast.domain.media.Media.default_track`), - иначе
    строка отбора и строка запуска называли бы разные языки одного файла.

    🔴 TC-492. Дорожка без тега языка называется «не назван», а не «оригинальный»: это
    ровно тот случай, ради которого гейт и бракует релиз (:func:`voice_unproven`), и
    придумывать ей язык в той же строке было бы второй такой же ошибкой.
    """
    if not media.tracks:
        return "не назван"
    index = media.default_track()
    track = media.tracks[index] if index < len(media.tracks) else media.tracks[0]
    return spoken(track) if track.named else "не назван"
