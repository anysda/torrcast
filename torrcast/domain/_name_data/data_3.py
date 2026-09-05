"""Часть таблиц разбора имён; используют чистые правила домена."""

from __future__ import annotations

import re
from typing import Final

from torrcast.domain._name_data.data_2 import _EPISODE_BRACKET_RE

_EPISODE_SPAN_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        "[eеэ]\\s*(?P<start>\\d{1,3})\\s*-\\s*[eеэ]?\\s*(?P<end>\\d{1,3})(?!\\d)\\s*(?:из|of)\\s*\\d{1,3}",
        re.IGNORECASE,
    ),
    re.compile(
        "(?<!\\d)(?P<start>\\d{1,3})\\s*-\\s*[eеэ]?\\s*(?P<end>\\d{1,3})(?!\\d)\\s*(?:из|of)\\s*\\d{1,3}",
        re.IGNORECASE,
    ),
    re.compile(
        "(?<!\\d)(?P<start>\\d{1,3})\\s*-\\s*(?P<end>\\d{1,3})(?!\\d)\\s*сери", re.IGNORECASE
    ),
    re.compile("сери[ияй]\\s*(?P<start>\\d{1,3})\\s*-\\s*(?P<end>\\d{1,3})(?!\\d)", re.IGNORECASE),
    # Маркер серии - ОТДЕЛЬНАЯ буква, а не хвост предыдущего слова: иначе «Ice Age 1-5»
    # читается как «e 1-5» и сборник фильмов объявляется сериалом (TC-1033). Слово
    # «Episode» названо явно - оно кончается на ту же букву и маркером быть обязано.
    re.compile(
        "(?:\\bepisodes?|(?<![^\\W\\d_])[eеэ])"
        "\\s*(?P<start>\\d{1,3})\\s*-\\s*[eеэ]?\\s*(?P<end>\\d{1,3})(?!\\d)",
        re.IGNORECASE,
    ),
    _EPISODE_BRACKET_RE,
    # «N to M» без слова «серия»: англоязычная линейка серий («OVAs 1 to 4»).
    # Четырёхзначное начало не берём - «2001 to 2011» это годы, а не серии.
    re.compile("(?<!\\d)(?P<start>\\d{1,3})\\s+to\\s+(?P<end>\\d{1,3})(?!\\d)", re.IGNORECASE),
)
_EPISODE_COUNT_RE: Final = re.compile(
    "(?<!\\d)(?P<count>\\d{1,3})\\s*(?:из|of)\\s*(?P<total>\\d{1,3})(?!\\d)", re.IGNORECASE
)
_EPISODE_ONLY_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile("\\bep?\\.?\\s?(?P<episode>\\d{1,3})\\b(?!\\s*(?:сезон|мин))", re.IGNORECASE),
    re.compile("\\b(?P<episode>\\d{1,3})\\s*(?:из|of)\\s*\\d{1,3}\\b", re.IGNORECASE),
    re.compile("\\b(?P<episode>\\d{1,3})\\s*-?\\s*(?:я|ая)?\\s*сери", re.IGNORECASE),
)
_FANSUB_EPISODE_RE: Final = re.compile(
    "^\\[[^\\[\\]]+\\]\\s*(?P<name>[^\\[\\]()]+?)\\s+-\\s+(?P<episode>\\d{1,3})"
    "(?:\\s*-\\s*(?P<last>\\d{1,3}))?(?:v\\d)?\\s*(?=[\\[(]|$)"
)
VIDEO_EXT: Final = (".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".webm", ".m4v", ".mpg")
_JUNK_RE: Final = re.compile(
    "\\b(?:samples?|trailers?|трейлер\\w*|teasers?|creditless|nc-?(?:op|ed)|extras?|bonus\\w*|бонус\\w*|specials?|скриншот\\w*|screens?|proof|обложк\\w*)\\b|\\bop\\s*-\\s*ed\\b|[/\\\\](?:openings?|endings?|op|ed)[/\\\\]",
    re.IGNORECASE,
)
_TECH_TOKEN_RE: Final = re.compile(
    "^(?:\\d{3,4}[xх]\\d{3,4}|(?:19|20)\\d{2}|\\d+bit|\\d+fps|\\d+кбит|\\d+kbps|v\\d)$",
    re.IGNORECASE,
)
_SMALL_RATIO: Final = 0.35
_ANIME_RE: Final = re.compile(
    "\\bаниме\\b|\\banime\\b|с[еёо]?нэн|с[еёо]?дз[ёе]|сэйнэн|дз[её]сэй|\\bмеха\\b|этти|исекай|\\bsho[uw]?nen\\b|\\bshoujo\\b|\\bseinen\\b|\\bova\\b|\\bona\\b|\\[\\s*tv\\s*-?\\s*\\d?\\s*\\]|\\bтв-\\d",
    re.IGNORECASE,
)
_ANIME_INDEXERS: Final = ("nyaa", "anilib", "anidub", "animelayer")
_CODEC_TOKEN_RE: Final = re.compile(
    "\\b[xх]\\s?26[456]\\b|\\bh\\.?\\s?26[456]\\b|\\bavc\\b|\\bhevc\\b|\\bav1\\b|\\bvp9\\b|\\bdiv[x]\\b",
    re.IGNORECASE,
)
_SERIES_HINT_RE: Final = re.compile(
    "\\d+\\s*(?:из|of)\\s*\\d+|сери[ия]\\b|сезон|\\bseason\\b|\\bs\\d{1,2}\\b|\\bсериал|\\[tv\\]"
    # Слова полного сериала без всяких номеров: «Complete Series», итальянское
    # «[COMPLETA]», ньяшное «[Batch]» - это имя говорит о виде, а не о сериях.
    # Маркер «ТВ-N» из КРУГЛЫХ скобок не читается: там за голосовым тегом стоит студия,
    # и «Dub (ТВ-3)» зовёт телеканал, а не форму, - её пишут «[ТВ-3]» или хвостом имени.
    "|complete\\s+series|\\bcompleta\\b|\\bbatch\\b|(?<!\\()\\bтв-\\d",
    re.IGNORECASE,
)
_GLUE: Final = re.compile("(?<=[0-9a-zа-яё])[;:/\\\\|+&,~*=](?=[0-9a-zа-яё])", re.IGNORECASE)
_NUMERO_RE: Final = re.compile("\\s*№\\s*(?=\\d)")
_NUMERALS: Final = {
    "один": "1",
    "одна": "1",
    "одно": "1",
    "one": "1",
    "два": "2",
    "две": "2",
    "two": "2",
    "три": "3",
    "three": "3",
    "четыре": "4",
    "four": "4",
    "пять": "5",
    "five": "5",
    "шесть": "6",
    "six": "6",
    "семь": "7",
    "seven": "7",
    "восемь": "8",
    "eight": "8",
    "девять": "9",
    "nine": "9",
    "десять": "10",
    "ten": "10",
    "одиннадцать": "11",
    "eleven": "11",
    "двенадцать": "12",
    "twelve": "12",
    "тринадцать": "13",
    "thirteen": "13",
    "четырнадцать": "14",
    "fourteen": "14",
    "пятнадцать": "15",
    "fifteen": "15",
    "шестнадцать": "16",
    "sixteen": "16",
    "семнадцать": "17",
    "seventeen": "17",
    "восемнадцать": "18",
    "eighteen": "18",
    "девятнадцать": "19",
    "nineteen": "19",
    "двадцать": "20",
    "twenty": "20",
}
_FRANCHISE_MIN: Final = 2
_CHANNEL_RE: Final = re.compile(
    "^(?:bbc|discovery|national\\s+geographic|nat\\s+geo(?:\\s+wild)?|animal\\s+planet|pbs|nhk|arte|би-би-си)\\s*[.:]\\s+(?=\\S)",
    re.IGNORECASE,
)
_TRANSLIT: Final[dict[str, str]] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}
_SPELL_X: Final = re.compile("x")
_STEM: Final = 4
_ENDING: Final = 2
_TITLE_NUMBER_RE: Final = re.compile(
    "(?:[.:]|\\b(?:vol|volume|part|pt|chapter|book|эпизод|часть|ч|глава|том|книга|кн))\\s*$",
    re.IGNORECASE,
)
_SUBTITLE_RE: Final = re.compile("\\s*:\\s*|,\\s+или\\s+")
