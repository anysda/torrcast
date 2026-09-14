"""Строки выбора озвучки на карточке: дорожки раздачи на языке страницы.

Состав тот же, что печатает ``cast voices`` (:func:`torrcast.usecases.rank.voices_table.
voices_table`), а язык дорожки назван словом каталога языка СТРАНИЦЫ, а не процесса:
страница выбирает свой язык сама (:mod:`web.phrases`).
"""

from __future__ import annotations

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.catalogs.rank.en import en as rank_en
from torrcast.domain.catalogs.rank.ru import ru as rank_ru
from torrcast.domain.catalogs.select.en import en as select_en
from torrcast.domain.catalogs.select.ru import ru as select_ru
from torrcast.domain.catalogs.tongue import RU
from torrcast.domain.json_value import JsonValue
from torrcast.domain.track_studio import track_studio
from torrcast.usecases.rank.spoken_key import ORIGINAL_KEY, spoken_key
from web.heard import Heard


def card_voices(heard: Heard | None, lang: str) -> list[JsonValue]:
    """Строка на дорожку: подпись человеку, имя для ``voice`` и отметка дефолта.

    ``name`` - то, что ``--voice`` найдёт и в соседней раздаче: студия, если она у
    дорожки одна такая, иначе подпись дорожки (:func:`torrcast.usecases.rank.pick_voice.
    pick_voice` сравнивает с обеими).
    """
    if heard is None:
        return []
    media = heard.media
    catalog = {**rank_ru(), **select_ru()} if lang == RU else {**rank_en(), **select_en()}
    default = heard.default
    studios = [track_studio(media, t.index, heard.studios) for t in media.tracks]
    names = [studio.name.casefold() for studio in studios if studio is not None]
    rows: list[JsonValue] = []
    for track, studio in zip(media.tracks, studios, strict=True):
        label = _label(track, catalog)
        if studio is not None and studio.name.casefold() not in label.casefold():
            label = f"{label} ({studio.name})"
        unique = studio is not None and names.count(studio.name.casefold()) == 1
        name = studio.name if unique and studio is not None else track.label
        rows.append({"name": name, "label": label, "default": track.index == default})
    return rows


def _label(track: AudioTrack, catalog: dict[str, str]) -> str:
    """Язык словом каталога и заголовок раздачи; код вне каталога остаётся кодом."""
    key = spoken_key(track)
    language = ""
    if track.named:
        language = (track.language or "").strip() if key == ORIGINAL_KEY else catalog[key]
    parts = [part for part in (language, track.clean_title) if part]
    if parts:
        return " · ".join(parts)
    return catalog["select.track_number"].format(number=track.index + 1)


__all__ = ["card_voices"]
