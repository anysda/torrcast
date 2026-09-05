# ruff: noqa: E501
"""Часть таблиц разбора имён; используют чистые правила домена."""

from __future__ import annotations

import re
from typing import Final

_CYRILLIC: Final = re.compile("[а-яё]", re.IGNORECASE)
_UKRAINIAN: Final = re.compile("[іїєґ]", re.IGNORECASE)
_LATIN: Final = re.compile("[a-z]", re.IGNORECASE)
_QUALITY_RE: Final = re.compile("\\b(2160p|1080[pi]|720p|576p|480p|360p|4k|uhd)\\b", re.IGNORECASE)
_HEVC_RE: Final = re.compile("\\b(hevc|h\\.?\\s?265|x265)\\b", re.IGNORECASE)
_H264_RE: Final = re.compile("\\b(avc|h\\.?\\s?264|x264)\\b", re.IGNORECASE)
_MPEG4_RE: Final = re.compile(
    "\\b(xvid|divx|dx50|div3|3ivx|ms-?mpeg-?4|mpeg-?4|mp4v)\\b", re.IGNORECASE
)
_AV1_RE: Final = re.compile("\\bav1\\b", re.IGNORECASE)
_HDR_RE: Final = re.compile("\\b(hdr10\\+?|hdr|dolby\\s*vision|dv)\\b", re.IGNORECASE)
_STEREO_RE: Final = re.compile(
    "(?:\\b3d(?:[ ._-]*video)?\\b|\\b3д\\b|стереопар\\w*)", re.IGNORECASE
)
_STEREO_LAYOUT_RE: Final = re.compile(
    "\\b(?:h(?:alf)?|f(?:ull)?)[ ._-]*(?:sbs|ou)\\b|\\b(?:half|full)[ ._-]*(?:side[ ._-]*by[ ._-]*side|over[ ._-]*under)\\b",
    re.IGNORECASE,
)
_TWO_D_RE: Final = re.compile("\\b2d\\b|\\b2д\\b", re.IGNORECASE)
_AVI_RE: Final = re.compile("\\.avi\\b", re.IGNORECASE)
_EXTRAS_RE: Final = re.compile(
    "фильм[ае]? о фильме|как снимал\\w*|о съ[её]мках|за кадром|доп(?:олнительн\\w*|\\.)?\\s*материал\\w*|вырезанн\\w*\\s+сцен\\w*|бонус\\w*|интервью|трейлер\\w*|тизер\\w*|making[\\s._-]*of|behind[\\s._-]+the[\\s._-]+scenes?|deleted[\\s._-]+scenes?|\\bbonus\\b|\\bextras?\\b|\\bfeaturettes?\\b|\\btrailers?\\b|\\bteasers?\\b|\\binterviews?\\b",
    re.IGNORECASE,
)
_WITH_EXTRAS_RE: Final = re.compile("[+&]\\s*(?:\\d+\\s+)?$")
_EXTRAS_SURE_RE: Final = re.compile(
    "доп(?:олнительн\\w*|\\.)?\\s*материал\\w*|бонус\\w*[\\s._-]*диск\\w*|bonus[\\s._-]*disc",
    re.IGNORECASE,
)
_SOURCES: Final[tuple[tuple[str, str], ...]] = (
    ("bd-?remux|blu-?ray\\s*remux|uhd\\s*bdremux", "BDRemux"),
    ("\\bremux\\b", "Remux"),
    ("blu-?ray|bd-?rip", "BDRip"),
    ("web-?dl-?rip|web-?dlrip", "WEB-DLRip"),
    ("web-?dl", "WEB-DL"),
    ("web-?rip|\\bweb\\b", "WEBRip"),
    ("hd-?tv-?rip|hdtvrip|\\bhdtv\\b", "HDTV"),
    ("\\bhdrip\\b", "HDRip"),
    ("\\bvhs-?rip\\b|\\bvhs\\b", "VHSRip"),
    ("\\bsat-?rip\\b", "SATRip"),
    ("\\btv-?rip\\b", "TVRip"),
    ("dvd-?scr\\w*|\\bscreener\\b", "DVDScr"),
    ("dvd-?rip|\\bdvd\\d?\\b", "DVDRip"),
    ("\\bts\\b|\\bcam\\b|hdcam|telesync", "CAM"),
)
_HD_SOURCES: Final = frozenset(
    {"BDRemux", "Remux", "BDRip", "WEB-DL", "WEB-DLRip", "WEBRip", "HDTV", "HDRip"}
)
_SD_SOURCES: Final = frozenset({"DVDRip", "DVDScr", "VHSRip", "TVRip", "SATRip", "CAM"})
_VOICES: Final[tuple[tuple[str, str], ...]] = (
    ("гоблин\\b|пучков|goblin\\b", "Гоблин"),
    ("дубляж|дублир|(?<!no )\\bdub(?:bed|bing)?\\b|\\bдб\\b|лицензи|itunes", "Дубляж"),
    ("многоголос|\\bmvo\\b|\\bпм\\b|\\bлм\\b", "Многоголосый"),
    ("двухголос|\\bdvo\\b|\\bдвг\\b|\\bпд\\b|\\bлд\\b", "Двухголосый"),
    ("авторск|\\bavo\\b|\\bап\\b", "Авторский"),
    ("одноголос|\\bло\\b|\\bvo\\b", "Одноголосый"),
    ("субтитр|\\bsubs?\\b|\\bsubtitles?\\b|\\bст\\b", "Субтитры"),
    ("\\boriginal\\b|\\borig\\b|\\bориг", "Original"),
)
_TAG_VOICES: Final[dict[str, str]] = {
    "D": "Дубляж",
    "P": "Многоголосый",
    "P2": "Двухголосый",
    "A": "Авторский",
    "L": "Одноголосый",
}
_TAG_ONLY_RE: Final = re.compile(
    "^\\s*(?:\\d+\\s*[xх]\\s*)?[DPAL]2?(?:\\s*,\\s*(?:\\d+\\s*[xх]\\s*)?[DPAL]2?)*\\s*$"
)
_DUBBED: Final = frozenset(
    {"Гоблин", "Дубляж", "Многоголосый", "Двухголосый", "Авторский", "Одноголосый"}
)
_SUB_MENTION_RE: Final = re.compile(
    "multi\\s*\\d*\\s*-?\\s*subs?\\b|\\bsubs?(?:titles?)?\\s*(?:\\([^)]*\\)|\\[[^\\]]*\\])|\\b(?:rus|ru|рус\\w*|eng|ukr|укр)[\\s._+-]*subs?\\b|\\bsubs?(?:titles?)?[\\s._+-]*(?:rus|ru|рус\\w*|eng|ukr|укр)\\b|\\bsubs?(?:titles?)?\\b|субтитр\\w*",
    re.IGNORECASE,
)
_RU_AUDIO_RE: Final = re.compile("\\brus\\b|\\brussian\\b|\\bрус\\b|русск\\w*", re.IGNORECASE)
_LAYOUT: Final[dict[str, str]] = {
    "q": "й",
    "w": "ц",
    "e": "у",
    "r": "к",
    "t": "е",
    "y": "н",
    "u": "г",
    "i": "ш",
    "o": "щ",
    "p": "з",
    "[": "х",
    "]": "ъ",
    "a": "ф",
    "s": "ы",
    "d": "в",
    "f": "а",
    "g": "п",
    "h": "р",
    "j": "о",
    "k": "л",
    "l": "д",
    ";": "ж",
    "'": "э",
    "z": "я",
    "x": "ч",
    "c": "с",
    "v": "м",
    "b": "и",
    "n": "т",
    "m": "ь",
    ",": "б",
    ".": "ю",
    "`": "ё",
}
