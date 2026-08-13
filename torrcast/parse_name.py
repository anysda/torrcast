"""Парсер имён раздач и кластеризация франшиз.

Метаданных извне нет: всё, что мы знаем о картине, добывается из имени раздачи.
Три задачи: имя раздачи → :class:`Release` (название, оригинал, год, качество,
кодек, озвучки); релизы → :class:`Picture`-кластеры (франшиза = общее каноническое
название, сортировка по году даёт нумерацию); разбор эпизодов
``s01e05`` / ``2x5`` / «2 сезон 5 серия».

Разбор свой, не guessit. Форматы, которые модуль обязан понимать (проверено на
корпусе из 21 540 реальных имён):

* rutor/megapeer  ``Рус / Original (2024) BDRip 1080p от Кто-то | D, P, A``
* kinozal         ``Рус / Original / 2009 / ДБ, СТ / 4K, HEVC / Blu-Ray (2160p)``
* rutracker       ``Рус / Original (Режиссёр) [2009, США, боевик, BDRip] Dub + AVO``
* scene           ``The.Martian.2015.1080p.BluRay.x264-GRP``
* аниме           ``[Group] Title (2025) (WEB-DL 1080p H264) [ABCD1234] | alt``
"""

from __future__ import annotations

# fmt: off
__all__ = [
    "THIN_POOL", "TYPE_CHECKING", "VIDEO_EXT",
    "_ALTERNATIVE_PICTURE_RE", "_ALTERNATIVE_TITLE_RE", "_ANIME_INDEXERS",
    "_ANIME_RE", "_AV1_RE", "_AVI_RE",
    "_BRACKETS_RE", "_CHANNEL_RE", "_CHAPTER_RE",
    "_CODEC_TOKEN_RE",
    "_COLLECTION_CUT_RE",
    "_COLLECTION_LATIN",
    "_COLLECTION_RUSSIAN",
    "_CYRILLIC",
    "_DUBBED",
    "_ENDING",
    "_EPISODE_BRACKET_RE",
    "_EPISODE_COUNT_RE",
    "_EPISODE_ONLY_RES",
    "_EPISODE_SPAN_RES",
    "_EXTRAS_RE",
    "_EXTRAS_SURE_RE",
    "_FANSUB_EPISODE_RE",
    "_FOREIGN_DUB_RE",
    "_FOREIGN_LANG",
    "_FRANCHISE_MIN",
    "_GLUE",
    "_H264_RE",
    "_HDR_RE",
    "_HD_SOURCES",
    "_HEVC_RE",
    "_JUNK_RE",
    "_LATIN",
    "_LAYOUT",
    "_MERGED_TAIL",
    "_MPEG4_RE",
    "_NON_VIDEO_RE",
    "_NUMERALS",
    "_NUMERO_RE",
    "_OPEN_BRACKET_RE",
    "_PART_NUMBER_RE",
    "_QUALITY_RE",
    "_ROMAN",
    "_RU_AUDIO_RE",
    "_RU_CUT_WORDS",
    "_RU_EXT_RE",
    "_RU_STUDIO_RE",
    "_SD_SOURCES",
    "_SEASON_EPISODE_RES",
    "_SEASON_ONLY_RES",
    "_SEASON_SPAN_RES",
    "_SERIES_HINT_RE",
    "_SMALL_RATIO",
    "_SOURCES",
    "_SPELL_X",
    "_STEM",
    "_STEREO_LAYOUT_RE",
    "_STEREO_RE",
    "_SUB_MENTION_RE",
    "_TAG_ONLY_RE",
    "_TAG_VOICES",
    "_TECH_TOKEN_RE",
    "_TITLE_CUT_RE",
    "_TITLE_NUMBER_RE",
    "_TITLE_TAIL_RE",
    "_TRANSLIT",
    "_TWO_D_RE",
    "_UKRAINIAN",
    "_VIDEO_MARKER_RE",
    "_VOICES",
    "_WITH_EXTRAS_RE",
    "_YEAR_PATTERNS",
    "Counter",
    "Episode",
    "Final",
    "Iterable",
    "Kind",
    "Literal",
    "Picture",
    "Release",
    "Sequence",
    "_akin",
    "_paired",
    "_unbranded",
    "alt_query",
    "anime_indexer",
    "dataclass",
    "field",
    "franchise_key",
    "franchise_name",
    "in_digits",
    "looks_anime",
    "os",
    "part_number",
    "re",
    "same_word",
    "same_words",
    "slugify",
    "spell",
    "split_franchise_index",
    "transliterate",
    "unicodedata",
    "unswap_layout",
    "wire_query",
]
# fmt: on

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


import os.path
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Final, Literal

Kind = Literal["movie", "tv", "other"]

_CYRILLIC: Final = re.compile(r"[а-яё]", re.IGNORECASE)
_UKRAINIAN: Final = re.compile(r"[іїєґ]", re.IGNORECASE)
_LATIN: Final = re.compile(r"[a-z]", re.IGNORECASE)

_QUALITY_RE: Final = re.compile(r"\b(2160p|1080[pi]|720p|576p|480p|360p|4k|uhd)\b", re.IGNORECASE)
_HEVC_RE: Final = re.compile(r"\b(hevc|h\.?\s?265|x265)\b", re.IGNORECASE)
_H264_RE: Final = re.compile(r"\b(avc|h\.?\s?264|x264)\b", re.IGNORECASE)
#: MPEG-4 Part 2 (XviD/DivX и родня). Читается ПОСЛЕ H.264: «MPEG-4 AVC» - это H.264,
#: и порядок в :func:`_parse_codec` разводит их сам, без хитрых заглядываний вперёд.
_MPEG4_RE: Final = re.compile(
    r"\b(xvid|divx|dx50|div3|3ivx|ms-?mpeg-?4|mpeg-?4|mp4v)\b", re.IGNORECASE
)
_AV1_RE: Final = re.compile(r"\bav1\b", re.IGNORECASE)
_HDR_RE: Final = re.compile(r"\b(hdr10\+?|hdr|dolby\s*vision|dv)\b", re.IGNORECASE)
_STEREO_RE: Final = re.compile(
    r"(?:\b3d(?:[ ._-]*video)?\b|\b3д\b|стереопар\w*)",
    re.IGNORECASE,
)
_STEREO_LAYOUT_RE: Final = re.compile(
    r"\b(?:h(?:alf)?|f(?:ull)?)[ ._-]*(?:sbs|ou)\b|"
    r"\b(?:half|full)[ ._-]*(?:side[ ._-]*by[ ._-]*side|over[ ._-]*under)\b",
    re.IGNORECASE,
)
_TWO_D_RE: Final = re.compile(r"\b2d\b|\b2д\b", re.IGNORECASE)
#: Контейнер .avi в имени. Внутри .avi H.264 бывает, но на живой выдаче (36 раздач,
#: у которых удалось достать .torrent и заглянуть в имена файлов) все восемь .avi
#: оказались SD-рипами MPEG-4 - ни одного исключения.
_AVI_RE: Final = re.compile(r"\.avi\b", re.IGNORECASE)
#: Пометки, которыми раздача называет себя приложением к картине, а не самой картиной
#: (:attr:`Release.extras`). Все до одной сняты с живой выдачи: «… HDRip] фильм о фильме»,
#: «BDRip 720p | Дополнительные материалы», «HDRip 720р-Трейлер», «[Бонус-Диск]»,
#: «- интервью с актерами», «DCPRip-Тизер».
_EXTRAS_RE: Final = re.compile(
    r"фильм[ае]? о фильме|как снимал\w*|о съ[её]мках|за кадром|"
    r"доп(?:олнительн\w*|\.)?\s*материал\w*|вырезанн\w*\s+сцен\w*|бонус\w*|интервью|"
    r"трейлер\w*|тизер\w*|"
    r"making[\s._-]*of|behind[\s._-]+the[\s._-]+scenes?|deleted[\s._-]+scenes?|"
    r"\bbonus\b|\bextras?\b|\bfeaturettes?\b|\btrailers?\b|\bteasers?\b|\binterviews?\b",
    re.IGNORECASE,
)
#: Пометка приложения стоит ПОСЛЕ плюса - значит, раздача несёт и картину, и приложение
#: к ней: «[S01-05 + Extra]», «Тачки + Бонус», «Complete Series + Specials & Extras»,
#: «[01-80 + 3 extra]». Играть в такой раздаче есть что, и приложением она не считается.
_WITH_EXTRAS_RE: Final = re.compile(r"[+&]\s*(?:\d+\s+)?$")

#: Метки приложения, которые говорят «внутри не сама картина» без всякого веса:
#: «Дополнительные материалы», «бонус-диск». Список нарочно короткий: прочие метки
#: («бонус», «трейлер», «интервью», «фильм о фильме») носят и законные раздачи того,
#: что человек спросил, - у «Дюны: Части Третьей» единственная раздача это трейлер, а
#: документальное «Нечто: Ужас обретает форму» само фильм о фильме.
_EXTRAS_SURE_RE: Final = re.compile(
    r"доп(?:олнительн\w*|\.)?\s*материал\w*|бонус\w*[\s._-]*диск\w*|bonus[\s._-]*disc",
    re.IGNORECASE,
)

#: Источник картинки. Порядок важен: первый сработавший и есть ответ.
_SOURCES: Final[tuple[tuple[str, str], ...]] = (
    (r"bd-?remux|blu-?ray\s*remux|uhd\s*bdremux", "BDRemux"),
    (r"\bremux\b", "Remux"),
    (r"blu-?ray|bd-?rip", "BDRip"),
    (r"web-?dl-?rip|web-?dlrip", "WEB-DLRip"),
    (r"web-?dl", "WEB-DL"),
    (r"web-?rip|\bweb\b", "WEBRip"),
    (r"hd-?tv-?rip|hdtvrip|\bhdtv\b", "HDTV"),
    (r"\bhdrip\b", "HDRip"),
    # Плёночное и эфирное старьё. Стоит выше DVDRip намеренно: «VHSRip -> DVD» это
    # всё-таки VHS, а не DVD, и в выдаче честнее показать источник похуже.
    (r"\bvhs-?rip\b|\bvhs\b", "VHSRip"),
    (r"\bsat-?rip\b", "SATRip"),
    (r"\btv-?rip\b", "TVRip"),
    (r"dvd-?scr\w*|\bscreener\b", "DVDScr"),
    (r"dvd-?rip|\bdvd\d?\b", "DVDRip"),
    (r"\bts\b|\bcam\b|hdcam|telesync", "CAM"),
)

#: Источники, которые сами по себе означают HD-мастер: при неназванном кодеке этого
#: достаточно, чтобы релиз считался кандидатом в дефолт (:attr:`Release.prime`).
_HD_SOURCES: Final = frozenset({"BDRemux", "Remux", "BDRip", "WEB-DL", "WEB-DLRip", "WEBRip",
                                "HDTV", "HDRip"})  # fmt: skip

#: Источники, за которыми стоит мастер 720×576 и ниже. Такое почти всегда MPEG-4 в
#: .avi, но «почти» здесь принципиально: запрещать нельзя, можно только понижать
#: (:attr:`Release.dated`).
_SD_SOURCES: Final = frozenset({"DVDRip", "DVDScr", "VHSRip", "TVRip", "SATRip", "CAM"})

#: Маркеры озвучки: regex по всему имени → нормальная форма. Порядок = приоритет.
_VOICES: Final[tuple[tuple[str, str], ...]] = (
    (r"гоблин\b|пучков|goblin\b", "Гоблин"),
    # Тот же набор маркеров, что в лестнице дорожек (torrcast/stream.py:_VOICE_STEPS):
    # «Dubbed», «Movie Dubbing», «Лицензия», «iTunes». Страж «no » нужен, потому что
    # «no dub» - это отсутствие дубляжа; «undubbed» не срабатывает уже по \b.
    (r"дубляж|дублир|(?<!no )\bdub(?:bed|bing)?\b|\bдб\b|лицензи|itunes", "Дубляж"),
    (r"многоголос|\bmvo\b|\bпм\b|\bлм\b", "Многоголосый"),
    (r"двухголос|\bdvo\b|\bдвг\b|\bпд\b|\bлд\b", "Двухголосый"),
    (r"авторск|\bavo\b|\bап\b", "Авторский"),
    (r"одноголос|\bло\b|\bvo\b", "Одноголосый"),
    (r"субтитр|\bsubs?\b|\bsubtitles?\b|\bст\b", "Субтитры"),
    (r"\boriginal\b|\borig\b|\bориг", "Original"),
)
#: Односимвольные коды rutor/megapeer в хвосте ``| D, P, A``.
_TAG_VOICES: Final[dict[str, str]] = {
    "D": "Дубляж",
    "P": "Многоголосый",
    "P2": "Двухголосый",
    "A": "Авторский",
    "L": "Одноголосый",
}
_TAG_ONLY_RE: Final = re.compile(
    r"^\s*(?:\d+\s*[xх]\s*)?[DPAL]2?(?:\s*,\s*(?:\d+\s*[xх]\s*)?[DPAL]2?)*\s*$"
)
#: Виды перевода из :data:`_VOICES`, наличие которых в имени и есть обещание русской
#: ЗВУКОВОЙ дорожки. «Субтитры» и «Original» сюда не входят намеренно: читать титры
#: вместо озвучки решено не предлагать, а «оригинал» - это как раз то, чего не понять.
_DUBBED: Final = frozenset(
    {"Гоблин", "Дубляж", "Многоголосый", "Двухголосый", "Авторский", "Одноголосый"}
)

#: Упоминания субтитров: вычитаются из имени ДО поиска русской дорожки, иначе
#: «[JAP+Rus Sub]» и «Sub (Rus, Eng)» читались бы как русская озвучка. Языковая метка
#: СВОЕЙ дорожки при этом уцелеет: в «JAP+Sub» стирается только «Sub», а «JAP+» остаётся
#: и честно говорит, что звук японский.
_SUB_MENTION_RE: Final = re.compile(
    r"multi\s*\d*\s*-?\s*subs?\b"
    r"|\bsubs?(?:titles?)?\s*(?:\([^)]*\)|\[[^\]]*\])"
    r"|\b(?:rus|ru|рус\w*|eng|ukr|укр)[\s._+-]*subs?\b"
    r"|\bsubs?(?:titles?)?\b|субтитр\w*",
    re.IGNORECASE,
)

#: Русская дорожка названа языковой меткой. Живая выдача аниме держится ровно на них:
#: «[RUS(int)]» (дорожка внутри контейнера), «[RUS(ext), ENG, JAP+Sub]» (отдельным
#: файлом), «[RUS + JAP]». Голое ``ru`` сюда не годится - его дают адреса трекеров
#: («kinozal.ru») в хвосте имени.
_RU_AUDIO_RE: Final = re.compile(r"\brus\b|\brussian\b|\bрус\b|русск\w*", re.IGNORECASE)

#: Русская дорожка обещана ОТДЕЛЬНЫМ ФАЙЛОМ: «[RUS(ext), ENG, JAP+Sub]», «RUS (ext.)».
#: Метка вычитается из имени до поиска русской дорожки ровно по той же причине, по какой
#: вычитаются субтитры (:data:`_SUB_MENTION_RE`): в самом видео этой дорожки нет, а играть
#: звук из соседнего файла показ не умеет. Метка «int» рядом («[RUS(int), RUS(ext)]»)
#: уцелеет и честно скажет, что дорожка внутри контейнера есть тоже.
#:
#: 🔴 TC-301. «int» РЯДОМ и «int» ВНУТРИ ТЕХ ЖЕ СКОБОК - одно и то же обещание, и метку
#: «RUS(ext/int)» вычитать нельзя: у пака часть серий несёт русскую дорожку внутри
#: контейнера, и играется она как любая другая. Пока скобки съедались целиком, такая
#: раздача переставала обещать русское вовсе - то есть не попадала ни в хвост очереди
#: (:meth:`~torrcast.cli._Plan._dubbed_tail`), ни в вопрос соседу
#: (:meth:`~torrcast.cli._Bench._honest`). Живой случай: «Врата Штейна … [RUS(ext/int),
#: JAP+Sub] … [1080p]» - 86 сидов против 0-1 у всех остальных русских раздач картины.
_RU_EXT_RE: Final = re.compile(
    r"\b(?:rus(?:sian)?|рус\w*)\s*\(\s*ext(?![^)]*\bint\b)[^)]*\)", re.IGNORECASE
)

#: Студии русской озвучки аниме: у них имя студии - единственный маркер дорожки во всём
#: имени («... BDRip-HEVC 1080p | Shiza Project», «Naruto- Shippuuden - AniLiberty.TOP»).
#: Список нарочно короткий и из различимых имён: английские фан-саб-группы Nyaa
#: (SubsPlease, Judas, MTBB, Trix, Arid, QM) сюда попасть не должны ни при каких
#: обстоятельствах - у них японский звук и английские титры.
_RU_STUDIO_RE: Final = re.compile(
    r"anilib(?:ria|erty)|ani-?dub|shiza|animevost|ani-?media|anistar|anifilm|"
    r"animaunt|anirise|aniplague|aniomnia|persona\s*99|kansai|ancord|jaskier|"
    r"студийн\w*\s+банд\w*|studio\s*band|дядюшк\w*\s+шурик|кубик\s+в\s+кубе|"
    r"lostfilm|newstudio|alexfilm|hdrezka|amazing\s*dubbing",
    re.IGNORECASE,
)

#: Языки, которые в имени раздачи означают ЧУЖОЙ звук. Русского тут нет и быть не может:
#: список ровно затем и нужен, чтобы отличить чужую дорожку от нашей.
_FOREIGN_LANG: Final = (
    r"(?:eng|english|англ\w*|ita|ital\w*|spa|esp|lat|pt-?br|por|fre|fra|fren\w*|"
    r"ger|deu|jap|jpn|japanese|kor|korean|chi|zho|chinese|ara|arabic|hin|tur|"
    r"ukr|укр|kaz|каз|thai|tamil|malaysian|bahasa\s+melayu|multi\d*|dual)"
)

#: Дубляж, про который прямо сказано, что он ЧУЖОЙ: «[English Dub]», «[Multi-Dub]»,
#: «Dub (Ita)». Вычитается из имени вместе с субтитрами, иначе английский дубляж Nyaa
#: читался бы как русский: маркер ``dub`` в :data:`_VOICES` про язык не спрашивает,
#: потому что писан по русским трекерам, где чужого дубляжа в имени не бывает.
#:
#: 🔴 TC-301. Языки стоят и ПОСЛЕ слова «dub», а не только перед ним: «[Dub - Japanese ,
#: English , Arabic]» - это перечисление чужих дорожек, и русской среди них нет ни одной.
#: Пока читалось только «<язык> dub», такое имя обещало русский дубляж на ровном месте:
#: «[TekkenQ8] Spirited Away … [Dub - Japanese , English , Arabic]» на 64 сида вставал
#: верхом отбора по звуковой ступени (:func:`~torrcast.cli.sound_step`) и уверял человека,
#: что перевод у картины есть.
#:
#: Обратный порядок читается ТОЛЬКО через тире или двоеточие и только по названию языка:
#: «Dub-Nickelodeon» и «Dub (Rus, Eng)» - это студия и наша дорожка, и трогать их нельзя.
_FOREIGN_DUB_RE: Final = re.compile(
    rf"\b{_FOREIGN_LANG}[\s._+-]*(?:audio|dubs?|dubbed|voice)\b"
    rf"|\bdubs?\b\s*[-–:]\s*{_FOREIGN_LANG}\b(?:\s*[,+/]\s*{_FOREIGN_LANG}\b)*",
    re.IGNORECASE,
)

#: Не-видео: музыка, книги, игры. Срабатывает только при отсутствии видео-маркеров.
#:
#: 🔴 Игра подписывается и без ``repack``/``pc``: приставкой (``PS3``, ``Xbox 360``,
#: ``Wii``, ``Nintendo``) или словами про игровое видео. «Властелин колец: Битва за
#: Средиземье 2 ... | Cinematic video (2006) HD | P1» - нарезка роликов из игры, и видео
#: в ней действительно есть, только картиной она не является: разобранная как кино, она
#: вставала единственной подписанной номером частью франшизы и строила линейку
#: «Властелина колец» от себя. Голое ``switch`` маркером не становится нарочно: так
#: зовётся и кино («Switch», 2011), а без видео-маркеров в имени различить их нечем.
#:
#: 🔴 Платформу каталог пишет и по-русски: «РС», «ПК». «Черное зеркало 3 /
#: The Black Mirror 3 (2011) РС» - игра 2011 года, а латинского ``pc`` в имени нет:
#: разобранная как кино с номером части 3, она вставала третьей частью в линейке
#: сериала - рядом с её же подписанным латиницей близнецом «... (2011) PC-Лицензия»,
#: которого страж читал верно. Слово короткое, поэтому только целиком (``\b``):
#: внутри аббревиатур его никто не ищет.
_NON_VIDEO_RE: Final = re.compile(
    r"\b(flac|mp3|ape|wav|lossless|vinyl|аудиокнига|audiobook|"
    r"pdf|fb2|epub|djvu|mobi|rtf|azw3|cbz|cbr|"
    r"repack|gog|steam-?rip|pc|рс|пк|x64|iso|portable|crack|"
    r"ps[1-5]|psp|xbox|nintendo|wii|cinematic\s+video)\b",
    re.IGNORECASE,
)
_VIDEO_MARKER_RE: Final = re.compile(
    r"\b(2160p|1080p|720p|576p|480p|4k|uhd|bdrip|bdremux|remux|blu-?ray|web-?dl|"
    r"web-?rip|webrip|hdrip|dvd\d?|dvdrip|dvdscr|hdtv|hdtvrip|vhsrip|ntsc|pal|"
    r"hevc|x26[45]|h\.?26[45]|avc|s\d{1,2}e\d{1,3})\b",
    re.IGNORECASE,
)

#: Всё, что после этих токенов, к названию не относится.
#:
#: 🔴 Русское слово про сборник («трилогия», «коллекция», ...) режет имя, только когда
#: оно ЗАКРЫВАЕТ свой кусок: «Матрица: Трилогия / The Matrix», «Гарри Поттер. Коллекция
#: [8 фильмов]». Дальше по строке идёт родительный падеж - и это уже обычное слово
#: названия: «Трансформеры: Трилогия войн Праймов / Transformers: Prime Wars Trilogy»
#: обрезалось до «Трансформеры» вместе с оригинальным названием, и отдельный сериал
#: 2017 года приезжал безымянным тёзкой «Transformers: Animated» - с ним его и сшивало
#: по номеру сезона (TC-240). Латинское ``collection`` таких падежей не знает и режет
#: по-прежнему безусловно.
#:
#: 🔴 TC-327. Слова про сборник вынесены отдельными кусками (:data:`_COLLECTION_LATIN`,
#: :data:`_COLLECTION_RUSSIAN`) не ради красоты: по ним же читается, что раздача - СБОРНИК
#: (:attr:`Release.collection`). Список обязан быть один: заведи ему второй разбор - и
#: имя, обрезанное по «Трилогия», перестанет считаться сборником при первой же правке
#: одного списка мимо другого.
_COLLECTION_LATIN: Final = r"collection"
_COLLECTION_RUSSIAN: Final = r"кинотрилогия|трилогия|дилогия|квадрология|антология|коллекция"
_TITLE_CUT_RE: Final = re.compile(
    r"\b(?:bd-?remux|bd-?rip|remux|blu-?ray|web-?dl\w*|web-?rip|webrip|hdrip|"
    r"dvd-?rip|dvd\d?|hdtv\w*|hdcam|telesync|dvdscr|satrip|iptv|"
    r"2160p|1080p|720p|576p|480p|4k|uhd|hevc|x26[45]|h\.?\s?26[45]|avc|av1|"
    r"s\d{1,2}\s?e\d{1,3}|s\d{2}|season|сезон|complete|\d+\s*(?:из|of)\s*\d+|"
    rf"серии|серия|выпуск|{_COLLECTION_LATIN})\b"
    rf"|\b(?:{_COLLECTION_RUSSIAN})\b(?!\s+[^\W\d_])",
    re.IGNORECASE,
)
#: Имя обрезано ИМЕННО словом про сборник - значит за именем стоит не картина, а пачка
#: картин (:attr:`Release.collection`). Сверяется с тем, что вырезал :data:`_TITLE_CUT_RE`,
#: и потому спрашивает целое совпадение, а не вхождение.
_COLLECTION_CUT_RE: Final = re.compile(
    rf"^(?:{_COLLECTION_LATIN}|{_COLLECTION_RUSSIAN})$", re.IGNORECASE
)

#: Явная подпись другой картины или монтажа. Проверяется по полному имени раздачи:
#: жанр «пародия» обычно стоит уже после заголовка, а ``fanedit`` - рядом с качеством.
#: Имя озвучки сюда не входит: ``AVO (Goblin)`` остаётся дорожкой обычной картины.
_ALTERNATIVE_PICTURE_RE: Final = re.compile(
    r"\bпароди[яи]\b|\bфанатск\w*\s+верси\w*\b|\b(?:fan[ ._-]?edit)\b|"
    r"\bсмешн(?:ой|ый)\s+перевод\b",
    re.IGNORECASE,
)
_ALTERNATIVE_TITLE_RE: Final = re.compile(r"\(гоблин\)", re.IGNORECASE)
#: Те же русские метки, но списком слов: по ним :func:`_title_zone` узнаёт рез, за которым
#: через слэш стоит оригинальное название (TC-282). Список НЕ заводится второй раз -
#: он разбирается из :data:`_COLLECTION_RUSSIAN`, иначе две правки разойдутся.
_RU_CUT_WORDS: Final = frozenset(_COLLECTION_RUSSIAN.split("|"))
#: Мусорный хвост названия: релиз-группы и слова-пустышки.
_TITLE_TAIL_RE: Final = re.compile(
    r"(?:\s*[-|]\s*(?:aniliberty\.top|anilibria\w*|complete|extras?|full)\s*$)+", re.IGNORECASE
)
_BRACKETS_RE: Final = re.compile(r"[\[(][^\[\]()]*[\])]")
_OPEN_BRACKET_RE: Final = re.compile(r"[\[(]")
#: Явный номер части в самом названии: «Тачки 3», «Форсаж - 8», «Терминатор II: ...».
_PART_NUMBER_RE: Final = re.compile(r"^.+?[\s,-]+(\d{1,2}|[ivx]{1,4})(?=\s*[:.]|\s*$)", re.I)
#: Слова, которыми каталог подписывает ГЛАВЫ одной картины: «Дары Смерти: Часть II»,
#: «Deathly Hallows: Part 2». Список нарочно уже :data:`_TITLE_NUMBER_RE` (тот страж
#: разбирает ЗАПРОС и держится шире): «Оно: Глава 2» и «Звёздные войны: Эпизод IV» -
#: настоящие части франшизы, а «частью»/``part`` зовут половины одной работы. Само по
#: себе слово главу не доказывает - «Стражи Галактики. Часть 2» так названа ВТОРАЯ часть
#: франшизы; решает сиблинг «Часть 1» (:func:`_unchaptered`).
_CHAPTER_RE: Final = re.compile(r"\b(?:часть|part)$", re.IGNORECASE)
_ROMAN: Final[dict[str, int]] = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
}
_YEAR_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"[(\[]\s*((?:19|20)\d{2})(?:\s*[-/]\s*(?:19|20)\d{2})?\s*[,)\]]"),
    re.compile(r"(?:^|[/|,]\s*)((?:19|20)\d{2})(?:\s*-\s*(?:19|20)\d{2})?\s*(?=[/|,]|$)"),
    re.compile(r"(?<=[\s.])((?:19|20)\d{2})(?=[\s.])"),
)

#: Хвост сдвоенной серии: сцена кладёт двойной эпизод одним файлом - «S10E17E18»,
#: «S10E17_18», «10x17_18» («The Last One» у «Друзей»). Страж границы слова видел
#: за первым номером второй и не считал имя серией ВОВСЕ: файл молча выпадал из
#: списка, и пак, объявивший «сезоны 1-10: s1e1...s10e18», не мог отдать s10e17 -
#: серия лежала в раздаче, но не ложилась ни на какую пару «сезон, серия» (TC-205).
#: Берём ПЕРВЫЙ номер - тот же приём, что у «10x17&18» → s10e17: файл и есть
#: семнадцатая серия (заодно и восемнадцатая). Хвост читается только с разделителем
#: (``_``/``e``/``x``): слитный «S01E051080p» серией не становится, как и раньше.
_MERGED_TAIL: Final = r"(?:[_exх]\d{1,3})?"
_SEASON_EPISODE_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"\bs\s*(?P<season>\d{1,2})\s*[.\-_ ]?\s*e\s*(?P<episode>\d{1,3})" + _MERGED_TAIL + r"\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<season>\d{1,2})\s*[xх]\s*(?P<episode>\d{1,3})" + _MERGED_TAIL + r"\b",
        re.IGNORECASE,
    ),
    # Хвост слова забираем целиком: «5 серия» вырезается из запроса без остатка «...я».
    re.compile(r"(?P<season>\d{1,2})\s*сезон\D{0,14}?(?P<episode>\d{1,3})\s*сери\w*", re.I),
    re.compile(r"(?P<episode>\d{1,3})\s*сери\D{0,14}?(?P<season>\d{1,2})\s*сезон\w*", re.I),
)
_SEASON_ONLY_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bs\s?(?P<season>\d{1,2})\b(?!\s?e)", re.IGNORECASE),
    re.compile(r"(?P<season>\d{1,2})[-\s]*(?:й\s*)?сезон", re.IGNORECASE),
    re.compile(r"season\s*(?P<season>\d{1,2})", re.IGNORECASE),
)
#: Диапазон сезонов в имени раздачи: ``[S01-06]``, ``S01-S06``, «1-6 сезоны»,
#: «Сезоны: 1-8 из 8».
#:
#: ⚠️ Двоеточие после слова «сезон» само по себе диапазон сезонов НЕ означает: на
#: трекере им куда чаще открывают перечень СЕРИЙ одного сезона - «(5 сезон: 1-3 серии
#: из 3)», «(1-6 сезоны: 1-86 серии из 86)». Разводит их то, назван ли сезон ДО слова:
#: назван - за двоеточием серии (и сезон уже прочитан соседними разборами), не назван -
#: за двоеточием сами сезоны. Отсюда стражи ``(?<!\d)(?<!\d\s)``: без них «5 сезон: 1-3»
#: становился «сезонами 1-3», а «1-6 сезоны: 1-86» - «сезонами 1-86».
_SEASON_SPAN_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bs\s?(\d{1,2})\s*-\s*s?\s?(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s*-\s*(\d{1,2})\s*(?:сезон\w*|seasons?)\b", re.IGNORECASE),
    re.compile(
        r"(?<!\d)(?<!\d\s)\b(?:сезон\w*|seasons?)\s*:\s*(\d{1,2})\s*-\s*(\d{1,2})"
        r"(?:\s*(?:из|of)\s*\d{1,2})?\b",
        re.IGNORECASE,
    ),
)
#: Сквозной диапазон серий отдельной скобкой: ``[01-201]``, ``[202-252]``, ``(01-12)``.
#:
#: 🔴 TC-169. У длинного аниме сезон в имени называют не всегда, а серии сплошь и рядом
#: нумеруют СКВОЗНО через весь сериал, диапазоном в скобке и без единого слова «серии»:
#: «Гинтама / Gintama TV-1 [01-201] (2006)», «TV-2 [202-252] (2011)», «TV-8 [354-367]».
#: Такое имя не читалось вовсе - ни серий, ни сериальности, - и раздача с ПЕРВОЙ серией
#: становилась «фильмом», выпадая из разбора по сериям целиком. Замер на живой выдаче
#: «Gintama»: серию 1 не покрывала НИ ОДНА раздача из 162, при том что сама она лежала
#: в выдаче двумя строками.
#:
#: Голое «1-8» правило по-прежнему не читает (см. ``e``-диапазон выше) - стражи узкие:
#:
#: * диапазон занимает скобку ЦЕЛИКОМ, от ``[``/``(`` до ``]``/``)``: «1080p CR WEB-DL»
#:   и «HEVC 10bit» в скобке не одни, и правило их не видит;
#: * начало либо с ведущим нулём (``01``), либо трёхзначное (``202``): именно так
#:   подписывают серии, а номера частей франшизы («Форсаж [1-4]») не подписывают никак;
#: * числа не длиннее трёх цифр - «(2006-2012)» это годы, а не серии.
#:
#: Замер ложных срабатываний по всем кэшам стенда - в отчёте TC-169.
_EPISODE_BRACKET_RE: Final = re.compile(
    r"[\[(]\s*(?:[eеэ]p?\.?\s*)?(?P<start>0\d{1,2}|\d{3})\s*-\s*(?P<end>\d{1,3})\s*[\])]"
)
#: Серии, лежащие ВНУТРИ раздачи, по её имени. Порядок обязателен: сначала диапазон
#: («1-5 из 220» = серии 1...5), потом счёт («220 of 220» = все 220, то есть 1...220).
#: Прочитай их наоборот - и полный сезон превратился бы в одну серию, а огрызок в пак.
#: Числа ограничены тремя цифрами и обрамлены стражами ``(?<!\d)/(?!\d)``: без них
#: «(2005-2020)» в имени читалось бы как диапазон серий.
_EPISODE_SPAN_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"[eеэ]\s*(?P<start>\d{1,3})\s*-\s*[eеэ]?\s*(?P<end>\d{1,3})(?!\d)"
        r"\s*(?:из|of)\s*\d{1,3}",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<!\d)(?P<start>\d{1,3})\s*-\s*[eеэ]?\s*(?P<end>\d{1,3})(?!\d)\s*(?:из|of)\s*\d{1,3}",
        re.IGNORECASE,
    ),
    re.compile(r"(?<!\d)(?P<start>\d{1,3})\s*-\s*(?P<end>\d{1,3})(?!\d)\s*сери", re.IGNORECASE),
    re.compile(r"сери[ияй]\s*(?P<start>\d{1,3})\s*-\s*(?P<end>\d{1,3})(?!\d)", re.IGNORECASE),
    # Без «из/of»: ``S01E01-08``, ``E12-24``. Буква ``e`` обязательна - голое «1-8»
    # в имени раздачи чаще про части названия, чем про серии.
    re.compile(r"[eеэ]\s*(?P<start>\d{1,3})\s*-\s*[eеэ]?\s*(?P<end>\d{1,3})(?!\d)", re.IGNORECASE),
    _EPISODE_BRACKET_RE,
)
#: Счёт серий без диапазона: «220 of 220», «12 из 24» - в раздаче серии с первой по N.
_EPISODE_COUNT_RE: Final = re.compile(
    r"(?<!\d)(?P<count>\d{1,3})\s*(?:из|of)\s*(?P<total>\d{1,3})(?!\d)", re.IGNORECASE
)

#: Серия без номера сезона в имени файла: ``E05``, «05 из 24», «5 серия».
_EPISODE_ONLY_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bep?\.?\s?(?P<episode>\d{1,3})\b(?!\s*(?:сезон|мин))", re.IGNORECASE),
    re.compile(r"\b(?P<episode>\d{1,3})\s*(?:из|of)\s*\d{1,3}\b", re.IGNORECASE),
    re.compile(r"\b(?P<episode>\d{1,3})\s*-?\s*(?:я|ая)?\s*сери", re.IGNORECASE),
)
#: Фансабовская подпись серии: ``[Группа] Название - 12 [1080p ...]``. Так подписывают
#: ОДНУ серию SubsPlease, Erai-raws, ASW, Judas, LoliHouse, shincaps - то есть весь
#: анимешный раздел; ``v2`` после номера - перевыпуск той же серии.
#:
#: Стражи нарочно узкие, потому что «Название - 8» это ещё и номер части у кино
#: («Форсаж - 8»):
#:
#: * имя начинается с тега релиз-группы в квадратных скобках - у рутрекера и рутора
#:   имена начинаются с названия;
#: * между названием и номером - тире С ПРОБЕЛАМИ, а в самом названии до номера нет ни
#:   скобок, ни хвостов («3-nen» не тире с пробелами и потому не мешает);
#: * сразу за номером начинается технический блок в скобках или конец строки;
#: * в имени НЕТ года - иначе «[Группа] Форсаж - 8 (2017) BDRip» прочиталось бы как
#:   восьмая серия. Замер по кэшам стенда: правило ловит 149 имён из 2051, все до одной
#:   серии аниме, и ни в одной из них года нет.
_FANSUB_EPISODE_RE: Final = re.compile(
    r"^\[[^\[\]]+\]\s*(?P<name>[^\[\]()]+?)\s+-\s+(?P<episode>\d{1,3})(?:v\d)?\s*(?=[\[(]|$)"
)
#: Расширения видео: всё прочее в раздаче - субтитры, обложки и мусор.
VIDEO_EXT: Final = (".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".webm", ".m4v", ".mpg")
#: Файлы, которые серией не являются, даже если номер в имени есть: сэмплы, трейлеры,
#: опенинги/эндинги без титров (аниме-раздачи держат их отдельной папкой), бонусы.
_JUNK_RE: Final = re.compile(
    r"\b(?:samples?|trailers?|трейлер\w*|teasers?|creditless|nc-?(?:op|ed)|extras?|"
    r"bonus\w*|бонус\w*|specials?|скриншот\w*|screens?|proof|обложк\w*)\b|"
    r"\bop\s*-\s*ed\b|[/\\](?:openings?|endings?|op|ed)[/\\]",
    re.IGNORECASE,
)
#: Технический мусор в именах аниме: то, что похоже на номер серии, но им не является.
_TECH_TOKEN_RE: Final = re.compile(
    r"^(?:\d{3,4}[xх]\d{3,4}|(?:19|20)\d{2}|\d+bit|\d+fps|\d+кбит|\d+kbps|v\d)$", re.IGNORECASE
)
#: Доля от медианного размера, ниже которой файл раздачи серией не считается.
_SMALL_RATIO: Final = 0.35

#: Имя раздачи говорит, что внутри аниме. Список нарочно короткий и из того, что
#: значит ровно одно: слово «аниме»/«anime», японские жанры из шапки анимешного
#: раздела рутрекера (сёнэн, сёдзё, сэйнэн, меха, этти, исекай) и форматы, которых нет
#: больше нигде (OVA, ONA). Сюда же метка ``[TV]`` / ``[ТВ-2]``: так подписывает
#: сериалы ровно анимешный раздел, у обычного сериала в имени стоит ``[S01]``.
#:
#: Цена ошибки в обе стороны - секунды, а не подмена: признак отключает ОДНУ
#: прикидку по размеру (:func:`~torrcast.cli.is_dated`), а годность как решал, так и
#: решает ffprobe после выбора. Поэтому список и держится узким, а не «на всякий».
_ANIME_RE: Final = re.compile(
    r"\bаниме\b|\banime\b|с[еёо]?нэн|с[еёо]?дз[ёе]|сэйнэн|дз[её]сэй|\bмеха\b|этти|исекай|"
    r"\bsho[uw]?nen\b|\bshoujo\b|\bseinen\b|\bova\b|\bona\b|\[\s*tv\s*-?\s*\d?\s*\]|\bтв-\d",
    re.IGNORECASE,
)
#: Индексеры, у которых аниме - всё, что там лежит. Имя приходит от Prowlarr как есть.
_ANIME_INDEXERS: Final = ("nyaa", "anilib", "anidub", "animelayer")


def looks_anime(text: str) -> bool:
    """Текст (имя раздачи или поисковый запрос) прямо говорит про аниме.

    Тот же узкий список, что судит имена раздач (:data:`_ANIME_RE`): слово
    «аниме»/«anime», японские жанры, OVA/ONA, метка ``[TV]``.
    """
    return bool(_ANIME_RE.search(text))


def anime_indexer(name: str) -> bool:
    """Индексер, у которого аниме - всё, что там лежит (:data:`_ANIME_INDEXERS`)."""
    low = name.lower()
    return any(mark in low for mark in _ANIME_INDEXERS)


#: Токены кодека: цифры в них к сериям отношения не имеют. Вырезаются только в разборе
#: сериальности (:func:`_parse_series`) - сам кодек читается отдельно и раньше.
_CODEC_TOKEN_RE: Final = re.compile(
    r"\b[xх]\s?26[456]\b|\bh\.?\s?26[456]\b|\bavc\b|\bhevc\b|\bav1\b|\bvp9\b|\bdiv[x]\b",
    re.IGNORECASE,
)

#: Сериальность без номера сезона: «12 из 24», «E12 of 12», «[ТВ-2]».
#: Голое ``episode``/``tv`` сюда не годится - «Star Wars Episode I» это фильм.
_SERIES_HINT_RE: Final = re.compile(
    r"\d+\s*(?:из|of)\s*\d+|сери[ия]\b|сезон|\bseason\b|\bs\d{1,2}\b|"
    r"\bсериал|\[tv\]|\bтв-\d",
    re.IGNORECASE,
)


# Модель разобранного имени и языковые операции живут отдельно: таблицы признаков
# выше остаются одной предметной частью и передаются реализации как общий namespace.
from torrcast import parse_name_query as _parse_name_query  # noqa: E402
from torrcast.parse_name_query import (  # noqa: E402
    _CHANNEL_RE,
    _ENDING,
    _FRANCHISE_MIN,
    _GLUE,
    _LAYOUT,
    _NUMERALS,
    _NUMERO_RE,
    _SPELL_X,
    _STEM,
    _TITLE_NUMBER_RE,
    _TRANSLIT,
    THIN_POOL,
    Episode,
    Picture,
    Release,
    _akin,
    _paired,
    _unbranded,
    alt_query,
    franchise_key,
    franchise_name,
    in_digits,
    part_number,
    same_word,
    same_words,
    slugify,
    spell,
    split_franchise_index,
    transliterate,
    unswap_layout,
    wire_query,
)

_parse_name_namespace = {
    name: value for name, value in globals().items() if not name.startswith("__")
}
vars(_parse_name_query).update(_parse_name_namespace)
globals().update(
    (name, value) for name, value in vars(_parse_name_query).items() if not name.startswith("__")
)


class _ParseNameModule(ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if not name.startswith("__") and name in vars(_parse_name_query):
            setattr(_parse_name_query, name, value)


sys.modules[__name__].__class__ = _ParseNameModule
