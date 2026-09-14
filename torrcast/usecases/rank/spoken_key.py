"""Ключ каталога для языка дорожки; зовут :mod:`torrcast.usecases.rank.spoken` и карточка веба."""

from __future__ import annotations

from torrcast.domain.audio_track import AudioTrack

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
    "ukr": "rank.lang_ukrainian",
    "uk": "rank.lang_ukrainian",
    "rus": "rank.lang_russian",
    "ru": "rank.lang_russian",
    "russian": "rank.lang_russian",
}


#: Ключ, которым назван язык вне короткого списка.
ORIGINAL_KEY = "rank.lang_original"


def spoken_key(track: AudioTrack) -> str:
    """Ключ каталога для языка дорожки; вне списка - :data:`ORIGINAL_KEY`.

    Нужен тому, кто берёт каталог языка сам, а не языка процесса: страница говорит
    на своём (:mod:`web.card_voices`).
    """
    return _SPOKEN.get((track.language or "").strip().casefold(), ORIGINAL_KEY)


__all__ = ["ORIGINAL_KEY", "spoken_key"]
