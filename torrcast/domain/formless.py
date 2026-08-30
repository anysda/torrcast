"""Правило formless; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data.data_2 import _FORM_WORDS, _ROMAN


def _formless(key: str) -> str:
    """Ключ без слова формы: «Gekijouban X» и «X» это одна картина, а не две.

    🔴 Номер при слове формы - это НОМЕР ЧАСТИ, и снять его целиком значит подменить
    картину, а не свести двойника: «Naruto Movie 3» и «Naruto Movie 7» разные фильмы.
    Поэтому номер снимается только вместе со словом формы и только если после него
    уцелел подзаголовок: четвёртую часть «Bleach Movie 4: The Hell Verse» отличает от
    прочих `the-hell-verse`, а не четвёрка, и без четвёрки она сходится с
    «Gekijouban Bleach» по имени. Голое «Наруто Фильм 3» подзаголовка не имеет, номер
    там - всё, что о части сказано, и он остаётся ключом `наруто-3`.

    Пустой остаток не отдаётся: ключ «фильм» это всё, что о картине сказано.
    """
    parts = key.split("-")
    for start in range(len(parts)):
        for size in (2, 1):
            if "-".join(parts[start : start + size]) not in _FORM_WORDS:
                continue
            after = start + size
            word = parts[after] if after < len(parts) else ""
            number = (
                str(_ROMAN[word])
                if word in _ROMAN
                else word
                if word.isdigit() and len(word) <= 2
                else ""
            )
            tail = parts[after + (1 if number else 0) :]
            kept = parts[:start] + (tail or ([number] if number else []))
            return "-".join(kept) if kept else key
    return key


__all__ = ["_formless"]
