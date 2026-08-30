"""Как назвать язык дорожки вслух; зовут строки отбора и строка про звук."""

from __future__ import annotations

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.catalogs.phrase import phrase

#: Языковые коды ffprobe → ключ каталога. Список короткий и ровно про то, что живёт в
#: раздачах кино и аниме; чего в нём нет, называется «оригинальный».
_SPOKEN: dict[str, str] = {
    "jpn": "rank.lang_japanese",
    "ja": "rank.lang_japanese",
    "jap": "rank.lang_japanese",
    "eng": "rank.lang_english",
    "en": "rank.lang_english",
    "kor": "rank.lang_korean",
    "zho": "rank.lang_chinese",
    "chi": "rank.lang_chinese",
    "fra": "rank.lang_french",
    "fre": "rank.lang_french",
    "deu": "rank.lang_german",
    "ger": "rank.lang_german",
    "spa": "rank.lang_spanish",
    "ita": "rank.lang_italian",
}


def spoken(track: AudioTrack) -> str:
    """Как назвать язык дорожки вслух: «японский»; неизвестный — «оригинальный»."""
    key = _SPOKEN.get((track.language or "").strip().casefold(), "rank.lang_original")
    return phrase(key)
