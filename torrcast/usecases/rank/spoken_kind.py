"""Вид перевода дорожки вслух; зовёт строку про выбор озвучки.

:attr:`~torrcast.domain.audio_track.AudioTrack.kind` - не подпись, а ключ сравнения:
им судит лестница (:data:`torrcast.domain.audio_track._VOICE_STEPS`) и таблица студий
(:class:`torrcast.domain.studio.Studio`). Переводить сам ``kind`` нельзя - лестница и
студии сравнивают его строкой, и перевод молча сломал бы оба сравнения. Здесь - только
то, что о нём говорится человеку.
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.catalogs.phrase import phrase

#: Вид перевода → ключ каталога. Слово в русском каталоге - то же самое, каким
#: :attr:`~torrcast.domain.audio_track.AudioTrack.kind` называет себя всегда: перевод не
#: должен даже под русским языком отличаться от ключа сравнения побайтово.
_KIND: Final[dict[str, str]] = {
    "дубляж": "rank.kind_dub",
    "многоголосый": "rank.kind_multi",
    "двухголосый": "rank.kind_dual",
    "одноголосый": "rank.kind_mono",
}


def spoken_kind(kind: str) -> str:
    """Вид перевода на языке продукта; незнакомое слово - как есть, пустое - пусто."""
    key = _KIND.get(kind)
    return phrase(key) if key else kind
