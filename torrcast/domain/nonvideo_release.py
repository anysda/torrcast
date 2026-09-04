"""Раздача не-видео по имени (N1-N4): звук, картинки, текст/книга или игра.

Признак работает ТОЛЬКО как различитель, а не голое слово формата: наивная ловля
`MP3`/`FLAC` внутри имени убивала настоящие фильмы («Индиана Джонс и Часы Судьбы ...
ProRes 444 10-bit encode, MP3 RUS Dub 2.0/DTS-HD/AC-3 5.1»). Видео-примета имеет право
вето - раздача остаётся видео, если в имени есть хоть одна.

N5 (доп.материалы, «Bonus»/«фильм о фильме») сюда НЕ входит: слово стоит и в имени
обычного релиза с бонус-диском, и в имени самостоятельной работы, и отсев по нему
убил бы «Чернобыль: Зона отчуждения. Финал» целиком (9 раздач из 9, хвост
`[01-03 из 03 + Фильм о фильме]`). Отвергнуто числами, не переоткрывать.

Приметы пишут латиницей, а раздачи - нет: `МР3` с кириллическими `М` и `Р` проходил
целым, `4К`, `ВDRip`, `НЕVC` теряли вето. Имя поэтому приводится к латинице ДО сверки
(:func:`_latinise`), одинаково для вето и для примет не-видео.
"""

from __future__ import annotations

import re

_VIDEO_RE = re.compile(
    r"(?i)(?<![a-z])(bdrip|bd-rip|webrip|web-rip|web-?dl|hdrip|dvdrip|dvd-?rip|"
    r"bdremux|remux|hdtvrip|hdtv|tvrip|satrip|camrip|dvd5|dvd9|blu-?ray|bluray|"
    r"x264|x265|h\.?264|h\.?265|hevc|avc|av1|xvid|divx|prores|"
    r"\d{3,4}[pi]|4k|uhd|mkv|avi|mp4|m2ts|vob|iso)(?![a-z])"
)
_AUDIO_RE = re.compile(r"(?i)(?<![a-z])(ape|flac|mp3|wav|ogg|m4a|alac|dsd|tak|wv)(?![a-z])")
_IMAGE_RE = re.compile(
    r"(?i)(?<![a-z])(jpe?g|png|tiff|bmp|psd)(?![a-z])"
    r"|\[(?:art|wallpapers?|scans|cosplay|calendar)\]|обои|артбук|artbook"
)
_TEXT_RE = re.compile(
    r"(?i)(?<![a-z])(pdf|epub|fb2|djvu|cbr|cbz|mobi)(?![a-z])"
    r"|манга|манхва|комикс|light novel|ラノベ"
)
_GAME_RE = re.compile(
    r"(?i)(repack|gog-rip|steam-rip|\bpc\b\s*[|-]|\|\s*pc\b|"
    r"(?<![a-z])android(?![a-z])|(?<![a-z])apk(?![a-z]))"
)


#: Кириллические двойники латинских букв, по месту: `Р` в `МР3`, `К` в `4К`, `В` в
#: `ВDRip`, `р` в `1080р`. Буквы без пары (`Б`, `Д`, `Ф`) сюда не входят - токен с
#: такой буквой не приводится вовсе, и настоящее слово остаётся собой.
_TWINS = str.maketrans("АВЕІЈКМНОРСЅТУХаеорсухіјѕ", "ABEIJKMHOPCSTYXaeopcyxijs")
_TOKEN_RE = re.compile(r"[^\W_]+")
_CYRILLIC_RE = re.compile(r"[Ѐ-ԯ]")
_LATIN_OR_DIGIT_RE = re.compile(r"[A-Za-z0-9]")


def _latinise(name: str) -> str:
    """Кириллические двойники -> латиница, но только в токене, где алфавиты смешаны.

    Условия два, и оба куплены числом на корпусе-100. Приводится ТОЛЬКО токен, у
    которого все кириллические буквы - двойники: приведение по букве убивает настоящие
    слова, «Ха**рс**» и «ве**рс**ія» дают `pc`, «А**так**а» даёт `tak`, и это 12 живых
    картин. И ТОЛЬКО там, где в токене рядом стоит латиница или цифра: `МР3`, `4К`,
    `1080р`, `ВDRip` алфавиты мешают, а «ТАК» в заглавном заголовке - обычное слово.
    Чисто кириллических токенов, дающих примету, на корпусе-100 ноль.
    """

    def _fold(match: re.Match[str]) -> str:
        token = match.group()
        if not _LATIN_OR_DIGIT_RE.search(token):
            return token
        latin = token.translate(_TWINS)
        return token if latin == token or _CYRILLIC_RE.search(latin) else latin

    return _TOKEN_RE.sub(_fold, name)


def _is_nonvideo_release(name: str) -> bool:
    """Примета не-видео есть И ни одной видео-приметы нет - раздача не нужна продукту."""
    name = _latinise(name)
    if _VIDEO_RE.search(name):
        return False
    return bool(
        _AUDIO_RE.search(name)
        or _IMAGE_RE.search(name)
        or _TEXT_RE.search(name)
        or _GAME_RE.search(name)
    )


__all__ = ["_is_nonvideo_release", "_latinise"]
