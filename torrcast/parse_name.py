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

__all__ = ['THIN_POOL', 'TYPE_CHECKING', 'VIDEO_EXT', '_ALTERNATIVE_PICTURE_RE',
    '_ALTERNATIVE_TITLE_RE', '_ANIME_INDEXERS', '_ANIME_RE', '_AV1_RE', '_AVI_RE', '_BRACKETS_RE',
    '_CHANNEL_RE', '_CHAPTER_RE', '_CODEC_TOKEN_RE', '_COLLECTION_CUT_RE', '_COLLECTION_LATIN',
    '_COLLECTION_RUSSIAN', '_CYRILLIC', '_DUBBED', '_ENDING', '_EPISODE_BRACKET_RE',
    '_EPISODE_COUNT_RE', '_EPISODE_ONLY_RES', '_EPISODE_SPAN_RES', '_EXTRAS_RE',
    '_EXTRAS_SURE_RE', '_FANSUB_EPISODE_RE', '_FOREIGN_DUB_RE', '_FOREIGN_LANG', '_FRANCHISE_MIN',
    '_GLUE', '_H264_RE', '_HDR_RE', '_HD_SOURCES', '_HEVC_RE', '_JUNK_RE', '_LATIN', '_LAYOUT',
    '_MERGED_TAIL', '_MPEG4_RE', '_NON_VIDEO_RE', '_NUMERALS', '_NUMERO_RE', '_OPEN_BRACKET_RE',
    '_PART_NUMBER_RE', '_QUALITY_RE', '_ROMAN', '_RU_AUDIO_RE', '_RU_CUT_WORDS', '_RU_EXT_RE',
    '_RU_STUDIO_RE', '_SD_SOURCES', '_SEASON_EPISODE_RES', '_SEASON_ONLY_RES', '_SEASON_SPAN_RES',
    '_SERIES_HINT_RE', '_SMALL_RATIO', '_SOURCES', '_SPELL_X', '_STEM', '_STEREO_LAYOUT_RE',
    '_STEREO_RE', '_SUB_MENTION_RE', '_TAG_ONLY_RE', '_TAG_VOICES', '_TECH_TOKEN_RE',
    '_TITLE_CUT_RE', '_TITLE_NUMBER_RE', '_TITLE_TAIL_RE', '_TRANSLIT', '_TWO_D_RE', '_UKRAINIAN',
    '_VIDEO_MARKER_RE', '_VOICES', '_WITH_EXTRAS_RE', '_YEAR_PATTERNS', 'Counter', 'Episode',
    'Final', 'Iterable', 'Kind', 'Literal', 'Picture', 'Release', 'Sequence', '_akin', '_paired',
    '_unbranded', 'alt_query', 'anime_indexer', 'dataclass', 'field', 'franchise_key',
    'franchise_name', 'in_digits', 'looks_anime', 'os', 'part_number', 're', 'same_word',
    'same_words', 'slugify', 'spell', 'split_franchise_index', 'transliterate', 'unicodedata',
    'unswap_layout', 'wire_query']

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.catalog import _parse_voices as _parse_voices


import os.path
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

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


@dataclass(frozen=True, slots=True)
class Release:
    """Одна раздача после разбора имени."""

    raw_name: str
    title: str
    original: str | None = None
    #: Имена картины, стоящие в заголовке МЕЖДУ первым именем и оригиналом: «Одна из
    #: многих / Из многих / **Плюрибус** / Pluribus» (:func:`_split_titles`). Каноническим
    #: именем такое не становится и картины не склеивает - им только ищут (:func:`_by_alias`).
    aliases: tuple[str, ...] = ()
    year: int | None = None
    quality: str | None = None
    codec: str | None = None
    source: str | None = None
    hdr: bool = False
    voices: tuple[str, ...] = ()
    season: int | None = None
    episode: int | None = None
    #: Сезоны пака целиком: ``[S01-06]`` → (1...6). Пусто - сезон один или не назван.
    seasons: tuple[int, ...] = ()
    #: Серии, которые лежат ВНУТРИ раздачи, по её имени: ``[S01E01-08 of 220]`` → (1...8),
    #: ``[E220 of 220]`` → (1...220). Пусто - имя о серияx молчит, и решат файлы.
    episodes: tuple[int, ...] = ()
    size: int = 0
    seeders: int = 0
    magnet: str = ""
    indexer: str = ""
    kind: Kind = "movie"
    #: Сколькими строками выдачи приехала раздача (:attr:`~torrcast.search.RawResult.copies`):
    #: зеркалящие друг друга индексеры несут один торрент по разу каждый.
    copies: int = 1
    #: ВСЕ индексеры, принёсшие раздачу (:attr:`~torrcast.search.RawResult.indexers`), а не
    #: только тот, чья строка выиграла склейку. Пусто - раздача приехала одной строкой, и
    #: всё, что о ней известно, стоит в :attr:`indexer`.
    indexers: tuple[str, ...] = ()
    #: ВСЕ имена, под которыми приехала раздача (:attr:`~torrcast.search.RawResult.names`),
    #: а не только то, что выиграло склейку. Признаки имён (:attr:`external_dub`) читаются
    #: отсюда: один торрент подписан у разных индексеров по-разному, и то, что сказал о
    #: раздаче каталог, складывается, а не выбирается вместе с именем победителя. Пусто -
    #: раздача приехала одной строкой, и всё, что известно, стоит в :attr:`raw_name`.
    names: tuple[str, ...] = ()
    #: Раздача - СБОРНИК нескольких картин: имя обрезано словом «Трилогия», «Коллекция»,
    #: ``Collection`` (:data:`_COLLECTION_CUT_RE`). Не оценка качества раздачи, а ответ на
    #: один вопрос: то, что стоит за именем, - это картина или пачка картин.
    collection: bool = False

    @property
    def is_hevc(self) -> bool:
        """HEVC показываем с пометкой ⚠ и никогда не берём по умолчанию."""
        return self.codec == "HEVC"

    @property
    def height(self) -> int:
        """Высота кадра из качества; 0 — качество в имени не указано."""
        digits = (self.quality or "").rstrip("pi")
        return int(digits) if digits.isdigit() else 0

    @property
    def interlaced(self) -> bool:
        """Имя обещает чересстрочный, а не прогрессивный кадр."""
        return bool(self.quality and self.quality.endswith("i"))

    @property
    def stereoscopic(self) -> bool:
        """Видео может приехать половиной стереопары вместо обычного кадра."""
        if _STEREO_LAYOUT_RE.search(self.raw_name):
            return True
        tail = self._untitled
        return bool(re.search(r"\b3д\b", self.raw_name, re.IGNORECASE)) or (
            not _TWO_D_RE.search(tail) and bool(_STEREO_RE.search(tail))
        )

    @property
    def prime(self) -> bool:
        """Релиз первого сорта — из таких выбирается дефолт. Кодек назван —
        годится только H.264. Кодек не назван (а это норма: у «Моаны 2» он есть в 2 именах
        из 8) — верим источнику и качеству: HD-мастер или ≥720p. DVDRip и CAM не годятся,
        иначе обсиженный DVDRip обгоняет живой 1080p.
        """
        if self.codec:
            return self.codec == "H.264"
        return self.height >= 720 or self.source in _HD_SOURCES

    @property
    def quiet(self) -> bool:
        """Имя о качестве МОЛЧИТ: ни разрешения, ни кодека — спорить с ним нечем.

        Отличается от «не первого сорта» (:attr:`prime`) тем, чего в имени нет, а не
        тем, что в нём плохого. HEVC, MPEG-4, «480p» — это имя, сказавшее о себе правду,
        и ворота отбора держат такое снаружи по делу. А «Наруто (S1) / Naruto [TV]
        [E220 of 220] [RUS(ext), ENG, JAP+Sub] [2002 … DVDRip]» — 157 ГБ, 91 сид, полный
        сериал — не говорит о качестве ничего, и у аниме такие имена сплошь: у той же
        картины единственные «именные» кандидаты имеют 3 и 1 сид.

        Молчание — не оценка, а отсутствие оценки, поэтому судить такую раздачу
        должен ffprobe после выбора, а не ворота до него
        (:func:`~torrcast.cli.gate_open`).
        """
        return not self.codec and not self.height

    @property
    def dubbed(self) -> bool:
        """Имя обещает РУССКУЮ звуковую дорожку.

        Три независимых сигнала, и все три взяты с живой выдачи:

        1. вид перевода из имени (:data:`_DUBBED`) — «Дубляж», «MVO», хвост rutor ``| D``;
        2. языковая метка ``RUS`` — «[RUS(int)]», «[RUS + JAP]»;
        3. имя студии озвучки (:data:`_RU_STUDIO_RE`) — «| Shiza Project», «AniLiberty.TOP»:
           у аниме это сплошь и рядом единственный маркер дорожки во всём имени.

        Из имени заранее вычитаются три вещи, каждая — по живому промаху:

        * субтитры (:data:`_SUB_MENTION_RE`): «Sub (Rus, Eng)» и «JAP+Rus Sub» — это
          титры, а не озвучка, и обещанием русского звука они не являются;
        * чужой дубляж (:data:`_FOREIGN_DUB_RE`): «[Yameii] Chainsaw Man … [English Dub]»
          и «[Funimation] Steins Gate 0 [Multi-Dub][ESP-LAT][PT-BR]» — дубляж там есть,
          только не тот;
        * 🔴 TC-191: дорожка отдельным файлом (:attr:`external_dub`, :data:`_RU_EXT_RE`) —
          «[RUS(ext), ENG, JAP+Sub]». В самом видео её нет, и играть звук из соседнего
          файла показ не умеет: обещанием русской ОЗВУЧКИ ПОКАЗА это не является.
          Ровно на этом «Наруто» и уезжал по-японски: пак на 91 сид метку ``RUS(ext)``
          носил в имени, отбор читал её как русскую дорожку и до соседа с ``RUS(int)``
          (3 сида) не доходил.

        ⚠️ Это по-прежнему ОБЕЩАНИЕ имени, а не факт: имя врёт и молчит. Факт читает
        ffprobe уже после выбора, и релиз, у которого русской дорожки не оказалось,
        отбор бракует и идёт дальше по очереди (:meth:`~torrcast.cli._Bench.resolve`).
        """
        text = _RU_EXT_RE.sub(
            " ", _FOREIGN_DUB_RE.sub(" ", _SUB_MENTION_RE.sub(" ", self.raw_name))
        )
        if any(v in _DUBBED for v in _parse_voices(text)):
            return True
        return bool(_RU_AUDIO_RE.search(text) or _RU_STUDIO_RE.search(text))

    @property
    def external_dub(self) -> bool:
        """Имя обещает русскую дорожку ОТДЕЛЬНЫМ ФАЙЛОМ: «[RUS(ext), ENG, JAP+Sub]».

        🔴 TC-191. Аниме-раздачи пишут про звук прямым текстом, и разница между
        ``RUS(int)`` и ``RUS(ext)`` для зрителя решающая: в первом случае русская дорожка
        лежит внутри контейнера и играется, во втором - рядом, отдельным файлом, и показ
        такую не подмешивает. Считать её «русская есть» значит отдать зрителю японский
        звук под видом «включилось».

        Признак нужен не отбору, а ЧЕСТНОЙ СТРОКЕ (:func:`~torrcast.cli.sound_note`):
        отбор такой релиз годным не считает (:attr:`dubbed` метку вычитает), а человеку
        разница важна - «перевода нет вовсе» и «перевод есть, но отдельным файлом» это
        два разных ответа и два разных следующих шага.

        🔴 TC-382. Спрашиваются ВСЕ имена раздачи (:attr:`names`), а не то одно, что
        выиграло склейку: один и тот же торрент приходит от разных индексеров под
        разными именами - у одного «[RUS(ext), JAP+Sub]», у другого «| L2, L1», - и
        метка выживала, только если побеждало первое. Сказанное каталогом об одной
        раздаче складывается, а не выбирается вместе с именем победителя.
        """
        return any(_RU_EXT_RE.search(name) for name in self.names or (self.raw_name,))

    @property
    def anime(self) -> bool:
        """Внутри аниме — по имени раздачи (:data:`_ANIME_RE`) или по индексеру.

        Нужен ровно затем, что у аниме СВОЙ честный битрейт: серия идёт 24 минуты, а
        рисованная картинка жмётся в разы лучше живой съёмки, и 1-1.5 Мбит/с на серию
        там — норма 1080p, а не признак SD-рипа. Прикидка по размеру
        (:func:`~torrcast.cli.is_dated`) на этом жанре врёт дважды: она делит на типовые
        45 минут сериала, которых у серии аниме нет, и сравнивает с порогом, писанным
        по полнометражному кино.

        Индексер спрашивается вторым сигналом: у Nyaa и AniLibria аниме — всё, что там
        лежит, а имена раздач оттуда бывают вовсе без русских слов и жанров.

        🔴 TC-257: спрашиваются ВСЕ принёсшие индексеры (:attr:`indexers`), а не тот один,
        чья строка выиграла склейку. Один торрент лежит и у Nyaa, и у общего индексера, а
        склейка оставляет строку с победившим именем — то есть жанр решался бы алфавитом
        («Knaben» раньше «Nyaa.si»). На замере 100 сохранённых выдач признак так пропадал
        у 170 раздач на 6 аниме-запросах из 19: раздача с Nyaa выглядела обычным кино.
        """
        if any(anime_indexer(name) for name in (self.indexer, *self.indexers)):
            return True
        return looks_anime(self.raw_name)

    @property
    def dated(self) -> bool:
        """Имя прямо признаётся, что раздача — старьё: MPEG-4, .avi или SD-источник.

        Зачем отдельно от :attr:`prime`. ``prime`` — это ВОРОТА: не первый сорт — не
        кандидат в дефолт вовсе. ``dated`` — это только ПОРЯДОК: релиз остаётся годным
        и играется, если ничего лучше нет. Разница не косметическая: у картины может
        не быть ни одного релиза с маркером качества в имени (у «Моаны» 2016 кодек
        назван в 5 именах из 16), и запрет по эвристике оставил бы нас вообще без
        кандидатов — а показывать что-то надо.

        Почему признак живёт здесь, а не в ключе сортировки :func:`~torrcast.cli.rank_releases`:
        всё перечисленное читается ИЗ ИМЕНИ и больше ниоткуда, то есть это свойство
        разобранного релиза, ровно как ``prime``, ``height`` и ``is_hevc`` рядом. А то,
        для чего нужна длительность картины (мизерный битрейт при неназванном
        качестве), длительности здесь взять неоткуда — и живёт в cli, рядом с
        ``bitrate_of``, у которого та же зависимость.

        ⚠️ Признак срабатывает и на именах вроде «HDDVDRip»: ``_SOURCES`` читает в нём
        DVDRip. Специально не чиним — HD-DVD-рип 2007 года и правда не то, что стоит
        ставить первым, когда рядом лежит WEB-DL.
        """
        return (
            self.codec == "MPEG-4"
            or self.source in _SD_SOURCES
            or bool(_AVI_RE.search(self.raw_name))
        )

    @property
    def extras(self) -> bool:
        """Раздача сама, своим именем, называет себя ПРИЛОЖЕНИЕМ к картине, а не картиной.

        🔴 TC-290. Ворота отбора судили раздачу по разрешению, битрейту, живости и звуку —
        то есть по тому, КАК она снята, — и ни одна ступень не спрашивала, картина ли это
        вообще. «Тачки 2 / Cars 2 [2011, мультфильм, комедия, приключения, HDRip] фильм о
        фильме» на 0.4 ГБ проходили как обычный кандидат и из-за малого веса выглядели по
        битрейту даже скромно-прилично. Человек просит кино и получает получасовой ролик о
        съёмках — это подмена самой картины, и молчаливая.

        Метка ищется в имени БЕЗ собственных имён картины (:attr:`_untitled`), и это первое
        ограждение: «Твин Пикс: Вырезанные сцены», «Интервью», «Нечто: Ужас обретает форму»
        — картины, у которых такое слово стоит в их же названии, и приложением они не
        становятся. Второе ограждение — плюс: «[S01-05 + Extra]», «Тачки + Бонус»,
        «Complete Series + Specials & Extras» несут картину И приложение к ней, то есть
        играть в них есть что.

        Зачем отдельно от :func:`~torrcast.cli.is_extra`. Здесь — ПОРЯДОК: имя одно, без
        длительности, и права выкинуть раздачу у него нет — оно только уводит её под
        картину (:func:`~torrcast.cli.rank_releases`). ВОРОТА судят имя вместе с весом, и
        живёт это в cli, у которого есть длительность картины, — ровно та же развилка, что
        у :attr:`dated` и :func:`~torrcast.cli.is_dated`.
        """
        tail = self._untitled
        return any(
            not _WITH_EXTRAS_RE.search(tail[: found.start()]) for found in _EXTRAS_RE.finditer(tail)
        )

    @property
    def extras_sure(self) -> bool:
        """Метка приложения, которая не требует веса: «Дополнительные материалы»,
        «бонус-диск» (:data:`_EXTRAS_SURE_RE`).

        🔴 TC-339. Ворота (:func:`~torrcast.cli.is_extra`) судят метку вместе с весом, и
        тяжёлое приложение их проходит: «Титаник | Дополнительные материалы» на 11.6 ГБ,
        «Довод» на 22.5, «Хоббит: Приложения» на 19.2 - по битрейту это картины, а по
        имени - нет. Такой метке вес не нужен: ролик столько не весит НИКОГДА, и слово
        здесь сказало всё, что оно могло сказать.

        Список однозначных меток короткий нарочно - прочие («бонус», «трейлер»,
        «интервью») без веса не судятся, потому что их носят и раздачи самой картины.
        Картина, у которой других раздач нет, своего верха не теряет в любом случае:
        это ограждение ворот (:func:`~torrcast.cli.is_extra`), а не этого признака.
        """
        return self.extras and bool(_EXTRAS_SURE_RE.search(self._untitled))

    @property
    def _untitled(self) -> str:
        """Имя раздачи без собственных имён картины: остаётся одна зона пометок.

        Вырезаются ровно те имена, которые разобрал сам парсер (:attr:`title`,
        :attr:`original`, :attr:`aliases`), — другого списка того, как называется КАРТИНА,
        в раздаче нет. «Твин Пикс: Вырезанные сцены / Twin Peaks: The Missing Pieces (2014)
        BDRip 720p» после вырезания остаётся строкой «(2014) BDRip 720p», и метки в ней уже
        нет; «Тачки 2 / Cars 2 [2011 … HDRip] фильм о фильме» — остаётся с меткой.
        """
        tail = self.raw_name
        for name in (self.title, self.original, *self.aliases):
            if name:
                tail = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", " ", tail, flags=re.IGNORECASE)
        return tail

    def covers(self, season: int) -> bool:
        """Есть ли в раздаче нужный сезон — по её имени. Имя молчит о сезоне —
        считаем, что может быть: окончательный ответ дают файлы, а не название.
        """
        if self.seasons:
            return season in self.seasons
        return self.season in (None, season)

    def covers_episode(self, want: Episode) -> bool:
        """Есть ли в раздаче нужная СЕРИЯ — по её имени, до похода в рой.

        Ровно тот вопрос, на котором авто-выбор ловился: у «Наруто», «Локи» и
        «Сверхъестественного» верхом отбора стоял огрызок («8 серий из 220», одна серия
        аниме), а полный сезон лежал рядом строкой ниже. Огрызок отличается от пака
        своим же именем: ``[S01E01-08 of 220]`` честно говорит, что дальше восьмой в нём
        ничего нет. Прочитать это стоит ноль секунд, а узнать то же самое от файлов —
        метаданные по DHT, то есть 5-40 с и потраченная попытка из трёх.

        Имя молчит — отвечаем «может быть»: окончательный ответ дают файлы
        (:func:`map_episodes`), и понижать молчаливых нельзя, иначе у сериала,
        где ни одно имя не перечисляет серии, не осталось бы кандидатов вовсе.
        """
        if not self.covers(want.season):
            return False
        if self.episodes:
            return want.episode in self.episodes
        return self.episode in (None, want.episode)

    @property
    def episode_count(self) -> int:
        """Сколько серий в раздаче по её имени; 0 — имя не говорит.

        Нужен затем, что у сериала размер раздачи — это НЕ размер серии, и любая оценка
        битрейта по нему врёт кратно числу серий (:func:`~torrcast.cli.bitrate_of`).
        """
        if self.episodes:
            return len(self.episodes)
        return 1 if self.episode is not None else 0

    @property
    def collection_count(self) -> int | None:
        """Сколько фильмов в сборнике; ``None`` — имя числа не говорит."""
        if not self.collection:
            return 1
        low = self.raw_name.lower()
        for marker, count in (
            ("дилог", 2),
            ("трилог", 3),
            ("trilogy", 3),
            ("квадролог", 4),
        ):
            if marker in low:
                return count
        return None

    @property
    def slug(self) -> str:
        return slugify(self.title)

    @property
    def franchise(self) -> str:
        return franchise_key(self.title)


@dataclass(slots=True)
class Picture:
    """Картина — кластер релизов с общим каноническим названием и годом."""

    title: str
    year: int | None
    kind: Kind = "movie"
    original: str | None = None
    #: Явный номер части, если он был хоть в одном варианте перевода названия.
    part: int | None = None
    #: Второе имя картины, под которым её же раздачи лежат в каталоге отдельной кучкой
    #: (:func:`glue`). Пусто - склейки не было, имя в каталоге одно.
    also: str = ""
    #: Псевдонимы из заголовков своих же раздач, слагами: имена, стоящие между первым
    #: именем и оригиналом (:attr:`Release.aliases`). Не паспорт картины, а указатель для
    #: поиска - ни в меню, ни в склейку, ни в ключ они не идут (:func:`_by_alias`).
    aliases: tuple[str, ...] = ()
    releases: list[Release] = field(default_factory=list)
    #: Справка подтвердила отечественное происхождение картины.
    native: bool = False

    @property
    def key(self) -> str:
        """Ключ состояния: ``<тип>:<slug>:<год>``. Года в раздачах может не быть
        вовсе — тогда в slug добавляется оригинальное название, иначе два разных
        «Вторжения» без года слились бы в одну запись прогресса.
        """
        slug = slugify(self.title)
        if not self.year and self.original:
            slug = f"{slug}-{slugify(self.original)}"
        return f"{self.kind}:{slug}:{self.year if self.year else '0'}"

    @property
    def franchise(self) -> str:
        return franchise_key(self.title)

    @property
    def rows(self) -> int:
        """Строк выдачи за картиной: раздача от трёх индексеров - три строки.

        Не то же, что ``len(releases)``: там раздачи, склеенные по ``infoHash``, здесь -
        сколько их было до склейки. Мера тощести (:data:`THIN_POOL`) считается именно
        отсюда, потому что и порог мерился по строкам - см. его описание.
        """
        return sum(r.copies for r in self.releases)

    @property
    def collection(self) -> bool:
        """Картина - на самом деле СБОРНИК: все её раздачи назвали себя пачкой картин.

        🔴 TC-327. «Хоббит: Трилогия», «Гарри Поттер: Коллекция», «Хоббит / Властелин
        колец: Коллекция ... (2001-2014)» - имя такой раздачи обрезается по слову про
        сборник до голого имени франшизы, и в каталоге заводится картина «Хоббит (2001)»
        или «Гарри Поттер (2001)», которой не существует. Диапазон лет в имени схлопывается
        в первый год, поэтому гейт года такую кучку не разводит.

        Ровно все, а не большинство: одна честная раздача под тем же именем и годом - это
        уже картина, и сборники рядом с ней только пополняют её пул.
        """
        return bool(self.releases) and all(r.collection for r in self.releases)

    @property
    def seeders(self) -> int:
        return max((r.seeders for r in self.releases), default=0)

    @property
    def best_release(self) -> Release | None:
        """Дефолт меню: самый обсиженный среди релизов первого сорта (H.264, ≥720p);
        нет таких — просто самый обсиженный.
        """
        if not self.releases:
            return None
        return sorted(self.releases, key=lambda r: (not r.prime, -r.seeders, -r.size, r.magnet))[0]


@dataclass(frozen=True, slots=True)
class Episode:
    season: int
    episode: int

    def __str__(self) -> str:
        return f"s{self.season}e{self.episode}"


#: Знаки, которые Prowlarr ВЫРЕЗАЕТ из запроса перед индексером, ничего не подставляя
#: взамен (см. :func:`wire_query`). Апостроф, дефис и точка сюда не входят: их Prowlarr
#: доносит как есть, и «Ocean's Eleven» на живом стенде отдаёт больше строк, чем «Oceans».
_GLUE: Final = re.compile(r"(?<=[0-9a-zа-яё])[;:/\\|+&,~*=](?=[0-9a-zа-яё])", re.IGNORECASE)


def wire_query(query: str) -> str:
    """Запрос в том виде, в каком его переживёт Prowlarr: склеивающий знак → пробел.

    🔴 TC-129. Prowlarr санитайзит поисковую строку ПЕРЕД индексером и часть знаков
    просто удаляет, не ставя вместо них пробела. Замерено на живом стенде (Knaben,
    log level trace): на наш ``query=Steins%3BGate`` в Knaben уходит
    ``{"query":"SteinsGate"}`` - слово, которого нет ни в одном имени раздачи, и
    Knaben честно отдаёт ноль. Тот же круг по «Steins Gate» даёт 96 строк, и повтор
    ничего не меняет: троттлинга тут нет, ноль воспроизводится каждый раз за 0.3 с.

    Мы не вправе переписывать название человеку, но обязаны спросить так, чтобы ответ
    не потерялся: точка с запятой в «Steins;Gate» разделяет слова, и пробел на её месте
    значит ровно то же самое. Знаки, которые Prowlarr доносит целыми (точка, дефис,
    апостроф), не трогаем - на них выдача как раз ЖИВАЯ, а замена их пробелом стоила бы
    строк («F.R.I.E.N.D.S.» и «WALL-E» уезжают в Knaben как есть).

    Меняем только знак МЕЖДУ буквами: «(500) Days of Summer» и «Fast & Furious» уже
    несут пробелы, там резать нечего.
    """
    return _GLUE.sub(" ", query)


#: «№» перед числом - знак препинания, а не буквы: каталог вводит им номер, человек его
#: не набирает вовсе.
#:
#: 🔴 Убирается ДО ``NFKC``, и это весь смысл правила. Нормализация раскладывает U+2116 в
#: две латинские буквы, и «Легенда №17» становится «Легенда No17»: слаг ``легенда-no17``
#: с запросом «легенда 17» не сходится ни строкой, ни словами, ни цифрами, и картина
#: терялась целиком при живой выдаче в девять десятков сидов. То же ждало «Палату №6».
_NUMERO_RE: Final = re.compile(r"\s*№\s*(?=\d)")


def slugify(text: str) -> str:
    """Название → ключ состояния: нижний регистр, дефисы, без мусора; кириллица
    сохраняется, ключи русские (``movie:матрица:1999``).
    """
    plain = _NUMERO_RE.sub(" ", text)
    normalized = unicodedata.normalize("NFKC", plain).casefold().replace("ё", "е")
    return re.sub(r"[^0-9a-zа-я]+", "-", normalized).strip("-")


#: Числительные, которыми каталог подписывает ОДНУ И ТУ ЖЕ картину то цифрой, то словом.
#: Список короткий нарочно: это счётные слова, с которых начинается название, а не
#: словарь чисел. Больше двадцати в названиях считает уже не человек, а порядковый номер
#: серии, и путать их не надо.
_NUMERALS: Final = {
    "один": "1", "одна": "1", "одно": "1", "one": "1",
    "два": "2", "две": "2", "two": "2",
    "три": "3", "three": "3",
    "четыре": "4", "four": "4",
    "пять": "5", "five": "5",
    "шесть": "6", "six": "6",
    "семь": "7", "seven": "7",
    "восемь": "8", "eight": "8",
    "девять": "9", "nine": "9",
    "десять": "10", "ten": "10",
    "одиннадцать": "11", "eleven": "11",
    "двенадцать": "12", "twelve": "12",
    "тринадцать": "13", "thirteen": "13",
    "четырнадцать": "14", "fourteen": "14",
    "пятнадцать": "15", "fifteen": "15",
    "шестнадцать": "16", "sixteen": "16",
    "семнадцать": "17", "seventeen": "17",
    "восемнадцать": "18", "eighteen": "18",
    "девятнадцать": "19", "nineteen": "19",
    "двадцать": "20", "twenty": "20",
}  # fmt: skip


def in_digits(slug: str) -> str:
    """Слаг, где числительное СЛОВОМ записано цифрой: ``двенадцать-обезьян`` → ``12-обезьян``.

    Каталог подписывает число как придётся, и одна картина рассыпается на две кучки
    ровно по этому шву. Живой случай, ради которого написано: «Двенадцать обезьян»
    (1995) приезжает 35 строками, из них 29 раздач под именем «12 обезьян» (до 105
    сидов) и ОДНА - под именем прописью, образ диска на 4 сида. Имена как строки
    разные, поэтому :func:`glue` их не сшивал, а :func:`pick_franchise` по запросу
    прописью отдавал ту самую единственную раздачу: в меню выходило «раздач 1» при
    живой выдаче в тридцать.

    Замена пословная и только по точному совпадению слова: «двенадцать» - число,
    а «двенадцатая ночь» или «семья» - уже нет, и трогать их незачем.
    """
    return "-".join(_NUMERALS.get(word, word) for word in slug.split("-"))


#: Сколько знаков обязано остаться от названия, чтобы хвостовое число считалось номером
#: части. Франшизы из одной буквы не бывает: «Т-34» - это марка танка, а не тридцать
#: четвёртая часть серии «Т». Без порога картина уезжала во франшизу с ключом ``т``, где
#: ей соседями становились любые другие однобуквенные огрызки, а номером пункта меню -
#: тридцать четыре.
_FRANCHISE_MIN: Final = 2


#: Каналы, которыми каталог подписывает документалистику СПЕРЕДИ: «BBC. Живая планета»,
#: «Discovery. Смертельный улов», «BBC: Планета Земля 3». Это не часть названия и не
#: подзаголовок, а марка вещателя, и франшизой картины ей быть незачем.
#:
#: ⚠️ Требуется знак после имени канала - точка или двоеточие с пробелом. Без него имя
#: канала вполне может быть первым словом самого названия: «BBC Proms», «BBC Springwatch»,
#: «BBC Arena» лежат в каталоге ровно так, и резать у них нечего.
_CHANNEL_RE: Final = re.compile(
    r"^(?:bbc|discovery|national\s+geographic|nat\s+geo(?:\s+wild)?|animal\s+planet"
    r"|pbs|nhk|arte|би-би-си)\s*[.:]\s+(?=\S)",
    re.IGNORECASE,
)


def _unbranded(title: str) -> str:
    """Название без марки вещателя спереди (:data:`_CHANNEL_RE`); нечего резать - как было."""
    return _CHANNEL_RE.sub("", title.strip(), count=1)


def franchise_key(title: str) -> str:
    """Каноническое имя франшизы: «Матрица: Перезагрузка» и «Тачки 3» → одна серия.
    Режем подзаголовок после двоеточия и хвостовой номер части — именно они
    отличают фильмы внутри франшизы.
    """
    return slugify(franchise_name(title)) or slugify(title)


def franchise_name(title: str) -> str:
    """То же, что :func:`franchise_key`, но читаемым текстом: «Cars 3» → ``Cars``.

    ⚠️ Подзаголовок советское кино вводит не двоеточием, а словом «или»: «Кавказская
    пленница, или Новые приключения Шурика», «Ирония судьбы, или С лёгким паром!». Без
    этого разреза классика Гайдая жила в каталоге под своим ключом, а короткий запрос
    «кавказская пленница» точно попадал в ключ РЕМЕЙКА 2014 года - и человек, спросивший
    классику, молча получал ремейк, хотя 22 раздачи оригинала лежали в той же выдаче.

    🔴 TC-297. Имя КАНАЛА спереди подзаголовком не считается (:data:`_CHANNEL_RE`).
    Документалистику каталог подписывает «BBC. Живая планета / BBC. The Living Planet
    (1984)», и разрез по точке оставлял от названия ровно ``BBC``: франшизой картины
    становился канал, в одну кучу с ней сваливались «BBC. Океаны» и всё остальное
    вещание, а запрос «живая планета» не попадал в такой ключ вовсе. Дальше добор шёл
    вторым именем ``BBC`` - строкой, по которой приезжает какое угодно кино, кроме
    спрошенного, - и человек честно читал «по BBC приехала другая картина».
    """
    base = re.split(r"\s*:\s*|\.\s+|,\s+или\s+", _unbranded(title), maxsplit=1)[0]
    # Хвост «3», «- 8», «II», а также диапазон «1-4» у сборников.
    cut = re.sub(
        r"[\s,-]+(?:\d{1,2}(?:\s*[-,]\s*\d{1,2})*|[ivx]{1,4})\s*$", "", base, flags=re.IGNORECASE
    )
    if len(cut.rstrip(" -")) >= _FRANCHISE_MIN:
        base = cut
    return base.rstrip(" -")


def part_number(title: str) -> int | None:
    """Явный номер части в названии: «Тачки 3» → 3, «Терминатор II» → 2, иначе None.

    Номер после «Часть»/``Part`` здесь остаётся номером: по одному названию главу
    одной картины от второй части франшизы не отличить («Дары Смерти: Часть II»
    против «Стражи Галактики. Часть 2»). Это различие требует каталога целиком и
    стоит ступенью позже - :func:`_unchaptered`.
    """
    match = _PART_NUMBER_RE.match(title.strip())
    if not match:
        return None
    head = title[: match.start(1)]
    if len(head.rstrip(" ,-")) < _FRANCHISE_MIN:
        return None  # «Т-34», «В-2»: это марка, а не тридцать четвёртая часть франшизы
    if re.search(r"\d\s*[-,]\s*$", head):
        return None  # «Форсаж 1-4», «Матрица 1,2,3» - это диапазон, а не номер части
    token = match.group(1).lower()
    return int(token) if token.isdigit() else _ROMAN.get(token)


#: Ниже этого числа СТРОК выдачи (:attr:`Picture.rows`) пул картины считается тощим.
#: Число не с потолка: на живом каталоге у картины, найденной целиком, строк десятки
#: («Матрица» 59, «Бешеные псы» 69, «Клан Сопрано» 35), а у картины, до которой русский
#: запрос дотянулся лишь краем, - единицы («Птицы» 1, «Дилижанс» 1, «Дедвуд» 4, «Психо»
#: 10). Между этими кучами широкий провал, и порог стоит в нём: на полной выдаче второй
#: заход не случается вовсе.
#:
#: ⚠️ Строк, а не склеенных раздач - и это не мелочь. Замеры выше сняты общим запросом,
#: где зеркальный торрент приходил от каждого индексера отдельной строкой; склейка по
#: ``infoHash`` (:func:`~torrcast.search.merge`) те же выдачи ужимает на живом стенде со
#: 190 строк до 179 и со 176 до 136. Считай мы тощесть склеенными раздачами - порог
#: поехал бы вниз вслед за зеркальностью круга, и второй заход звался бы там, где
#: каталог полон. Каталог от способа опроса индексеров не меняется - значит и мера не
#: должна.
THIN_POOL: Final = 15

#: Кириллица → латиница. Не ГОСТ, а то, как русские названия пишут в именах раздач:
#: «Брат» → ``brat``, «Ёлки» → ``elki``, «Щи» → ``shchi``.
_TRANSLIT: Final[dict[str, str]] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}  # fmt: skip


#: Латиница → кириллица по РАСКЛАДКЕ клавиш, а не по звучанию: клавиша ``n`` на
#: русской раскладке печатает «т». Это не транслит и путать их нельзя - здесь
#: соответствие физическое.
_LAYOUT: Final[dict[str, str]] = {
    "q": "й", "w": "ц", "e": "у", "r": "к", "t": "е", "y": "н", "u": "г", "i": "ш",
    "o": "щ", "p": "з", "[": "х", "]": "ъ", "a": "ф", "s": "ы", "d": "в", "f": "а",
    "g": "п", "h": "р", "j": "о", "k": "л", "l": "д", ";": "ж", "'": "э", "z": "я",
    "x": "ч", "c": "с", "v": "м", "b": "и", "n": "т", "m": "ь", ",": "б", ".": "ю",
    "`": "ё",
}  # fmt: skip


def unswap_layout(text: str) -> str:
    """Запрос, набранный НЕ ПЕРЕКЛЮЧИВ раскладку: ``«nfxrb»`` → «тачки».

    ``cast nfxrb`` - это «тачки», набранные на английской раскладке, клавиша в клавишу.
    Раскладку забывают все и всегда, а цена промаха тут максимальная: человек читает
    отказ по картине, которая в каталоге лежит двумя десятками раздач.

    Перевод только в одну сторону (латиница → кириллица) и только по клавишам
    (:data:`_LAYOUT`). Обратная сторона не нужна: русскую строку индексеры и так
    находят, а «cars», набранное по-русски, дало бы «сфкы» - слово, которого нет
    ни в одном имени раздачи, и искать по нему нечего.

    ⚠️ Сама по себе эта функция НИЧЕГО не решает и звать её вслепую нельзя: у любой
    латинской строки есть кириллический двойник, и «cars» превратился бы в «сфкы».
    Кто и когда её зовёт, решает :func:`~torrcast.cli._search` - и зовёт ровно тогда,
    когда обычный поиск не принёс НИ ОДНОЙ строки. На живом каталоге это стоит ноль:
    у запроса, который что-то нашёл, второго захода не случается вовсе.
    """
    lowered = unicodedata.normalize("NFKC", text).casefold()
    return "".join(_LAYOUT.get(ch, ch) for ch in lowered)


def transliterate(text: str) -> str:
    """Русское название латиницей; латинские куски и цифры остаются как есть."""
    lowered = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", "".join(_TRANSLIT.get(ch, ch) for ch in lowered)).strip()


#: Латинская буква, у которой в русском написании ДВА равноправных двойника: «кс» и «з».
#: ``Xena`` - это и «Ксена», и «Зена», и обе записи в каталоге живые. Транслит возвращает
#: из «Ксены» ``ksena``, а оригинал в раздаче подписан ``Xena``: как строки они разные,
#: и картина, лежащая под русским именем «Зена», по запросу «Ксена» не находилась вовсе.
_SPELL_X: Final = re.compile(r"x")


def spell(text: str) -> str:
    """Нормализованная транслитерация: «Ксена» и ``Xena`` пишутся одинаково - ``ksena``.

    Простой транслит (:func:`transliterate`) сводит русское написание к латинскому
    буква в букву, но САМА латиница пишет один звук по-разному, и русский переносит его
    то так, то этак (:data:`_SPELL_X`). Нормализация убирает именно это расхождение,
    оставляя всё остальное как есть: это ключ для сверки имён, а не запрос в индексер.
    """
    return _SPELL_X.sub("ks", transliterate(text))


#: Сколько букв слова должны совпасть, чтобы это было одно слово в другой форме. Четыре -
#: это «шепот»/«шепоты» и «самурае»/«самураи», но не «крик»/«кран».
_STEM: Final = 4
#: Насколько хвосты слов вправе разойтись сверх общего начала: русское окончание.
_ENDING: Final = 2


def same_word(one: str, two: str) -> bool:
    """Одно ли это слово: та же строка, та же основа или та же строка другой азбукой.

    Формы слова человек путает свободно: «Робот мечты» вместо «Мечты робота», «Крики и
    шёпот» вместо «Шёпоты и крики». Общее начало от :data:`_STEM` букв и не больше
    :data:`_ENDING` букв хвоста сверх него - это окончание, а не другое слово.

    ⚠️ Транслит сводит русское слово с латинским, но НИКОГДА двух русских между собой:
    мягкий знак он съедает, и «мать» стала бы «матом». Поэтому по звучанию сверяются
    только слова из РАЗНЫХ азбук.
    """
    if one == two:
        return True
    if bool(_CYRILLIC.search(one)) != bool(_CYRILLIC.search(two)):
        one, two = spell(one), spell(two)
        if one == two:
            return True
    common = len(os.path.commonprefix([one, two]))
    return common >= _STEM and len(one) - common <= _ENDING and len(two) - common <= _ENDING


def same_words(want: str, base: str) -> bool:
    """Те же слова, только в другом порядке и в другой форме.

    Классику человек зовёт по памяти, а каталог со справкой подписывают её точно: фильм
    Бергмана лежит под именем «Шёпоты и крики», а спрашивают его «Крики и шёпот»; «Мечты
    робота» спрашивают «Робот мечты». Слово в слово такие имена не совпадают ничем.

    Сверка нарочно тесная, потому что она единственная не требует совпадения по порядку.

    * слов должно быть **поровну** и **каждому** найдётся пара. Иначе «Восхождение»
      совпало бы с «Ганнибал: Восхождение» - той самой подменой, которую ловит
      :func:`~torrcast.facts.akin`;
    * имён из одного слова это не касается вовсе: у них порядок переставлять нечего, а
      совпадение по началу приняло бы «Персону» за «Персонажа»;
    * слово ПЕРЕСТАВЛЕННОЕ отличается от своей пары только окончанием (:func:`same_word`),
      а слово, оставшееся на своём месте, обязано совпасть буква в букву.
    """
    return _paired(want.split("-"), base.split("-"))


def _paired(mine: Sequence[str], theirs: Sequence[str]) -> bool:
    """Каждому слову одного имени нашлась своя пара в другом, и лишних не осталось.

    🔴 Форма слова прощается только ПЕРЕЕХАВШЕМУ слову. Слово, стоящее на том же месте,
    сверяется целиком, и вот почему: «Кольца власти» - это сериал 2022 года, а «Кольцо
    власти» - фильм 2007-го, лежащий в той же выдаче. Имена различает ровно одна буква
    окончания, и прости мы её на месте, запрос молча уезжал бы в чужое кино. Переставленное
    слово - другое дело: «Робот мечты» против «Мечты робота» это не однофамильцы, а одно
    имя, названное по памяти, и порядок тут единственная разница по существу.
    """
    if len(mine) < 2 or len(mine) != len(theirs):
        return False
    left = list(enumerate(theirs))
    for here, word in enumerate(mine):
        pair = next(
            (
                spot
                for spot in left
                if word == spot[1] or (spot[0] != here and same_word(word, spot[1]))
            ),
            None,
        )
        if pair is None:
            return False
        left.remove(pair)
    return True


def alt_query(query: str, releases: Iterable[Release], known: str = "", native: str = "") -> str:
    """Чем ещё называется то, что спросили по-русски: запрос для второго захода.

    Зачем он вообще. Индексеры ищут по ИМЕНИ раздачи, а не по картине: половина
    каталога подписана только латиницей («Psycho.1960.1080p»), и русский запрос до неё
    не достаёт - человеку пришлось бы догадаться набрать «Psycho».

    Источники названия идут по убыванию доверия.

    1. ``known`` - оригинал из справки (:func:`~torrcast.facts.origin`). Он лучший, потому
       что отвечает про ТУ САМУЮ картину, а не про то, что попало в выдачу: «Кингсман:
       Секретная служба» так и находится, хотя в русской выдаче оригинала нет вовсе.
       Подзаголовок здесь не режется - справка уже развела картины между собой, и резать
       нечего.
    2. Оригинал из выдачи: раздачи вида «Психо / Psycho (1960)» несут его сами, и он
       точнее транслита («Психо» → ``Psycho``, а не ``psikho``).
    3. Транслит - когда выдачи нет вовсе и читать нечего; он выручает короткие имена
       русского кино, которые за рубежом так и подписывают (``Brat``). При полностью
       пустой выдаче длинное русское имя транслитом ничем не подтверждено: это не второе
       имя, а тот же запрос другими буквами, и заведомо пустого второго круга для него
       не бывает. Если первая выдача картину уже назвала, транслит остаётся последней
       попыткой - так находятся латинописанные релизы ``Vrata Shteyna``.

    Зеркальный случай - ``native``, русское имя картины из той же справки. Спросили
    латиницей («cars»), а половина каталога подписана по-русски: под именем ``Cars`` в
    выдаче лежит одна мёртвая раздача, а «Тачки» живут четырьмя. Догадаться набрать
    по-русски человек не обязан ровно так же, как и наоборот. Русское имя берётся ТОЛЬКО
    из справки: в выдаче под латинским именем его взять неоткуда - там его и нет.

    🔴 TC-399. Но сперва - оригинал из справки, если он отличается от запроса. Короткое
    обиходное имя («lain») - это не полное название (``Serial Experiments Lain``), и
    добор русским именем тут проигрывает дважды: русскоязычные индексеры отвечают
    дольше всех, и круг добора закрывается кворумом быстрых ДО их ответа, а под
    полным оригиналом та же картина лежит сотней раздач у быстрых. Правило ровно
    зеркальное русской ветке: латинский оригинал от справки, не совпадающий с
    запросом, сильнее русского имени; совпадающий («cars» → ``Cars``) нового круга
    не даст, и тогда берётся русское имя.

    Пустая строка - добирать нечем: имени на другом языке никто не назвал.

    ⚠️ Оригинал ИЗ ВЫДАЧИ берётся по франшизе, поэтому номер части у него отрезается
    (:func:`franchise_name`). Без этого побеждало имя самой многолюдной части, и на
    «тачках» второй заход уходил в «Cars 3»: раздач у третьей части больше всех. Добор
    приносил ещё сорок «Тачек 3» и ни одной «Тачки» 2006 года - а у той в русской выдаче
    только образы DVD, и в меню первая часть выглядела мёртвой при живом 1080p BluRay
    на 66 сидов, который лежал под именем ``Cars 2006``.

    ⚠️ Само по себе это название НИЧЕГО НЕ ДОКАЗЫВАЕТ. Русским именем «Восхождение»
    подписаны и картина Шепитько 1977 года, и китайская 2019-го, поэтому оригинал из
    выдачи вполне может оказаться чужим фильмом. Кто именно приехал по этому имени,
    решает гейт добора в :func:`~torrcast.cli._second_language`, а не эта функция.
    """
    wanted = slugify(query)
    if not _CYRILLIC.search(query):
        known = known.strip()
        if known and not _CYRILLIC.search(known) and slugify(known) != wanted:
            return known
        native = native.strip()
        return native if _CYRILLIC.search(native) and slugify(native) != wanted else ""
    if known and not _CYRILLIC.search(known) and slugify(known) != wanted:
        return known.strip()
    pool = list(releases)
    names = Counter(
        franchise_name(original)
        for release in pool
        if (original := release.original) and _akin(wanted, slugify(release.title))
    )
    for name, _count in names.most_common():
        if name and not _CYRILLIC.search(name) and slugify(name) != wanted:
            return name
    words = slugify(query).split("-")
    return transliterate(query) if pool or len(words) == 1 else ""


def _akin(wanted: str, slug: str) -> bool:
    """Один ли это фильм по slug: точное совпадение или вхождение в любую сторону
    («психо» ↔ «психо-2», «сияние» ↔ «сияние»).
    """
    return bool(wanted) and bool(slug) and (wanted in slug or slug in wanted)


#: Слова-показатели, после которых цифра - часть САМОГО названия, а не номер части
#: франшизы: «Kill Bill: Vol. 1», «Deathly Hallows: Part 2», «Дюна: Часть вторая».
#: Сюда же попадает голая точка или двоеточие: каталог вводит ими подзаголовок, и
#: «Vol.» перед цифрой без слова уже сказал всё, что нужно.
_TITLE_NUMBER_RE: Final = re.compile(
    r"(?:[.:]|\b(?:vol|volume|part|pt|chapter|book|эпизод|часть|ч|глава|том|книга|кн))\s*$",
    re.IGNORECASE,
)


def split_franchise_index(query: str) -> tuple[str, int | None]:
    """Отделить хвостовой номер франшизы: ``«матрица 2»`` → ``("матрица", 2)``. Номер —
    позиция в отсортированной по году франшизе, а не часть названия;
    год (четыре цифры) номером не считается.

    🔴 Цифра после слова-показателя номером НЕ считается. «Kill Bill: Vol. 1» уходил в
    индексер как ``Kill Bill: Vol.`` — имя, которым раздачу не подписывает никто, — и
    каталог терялся целиком ещё до кластеризации: искать по обрубку нечего. То же самое
    ждало «…: Part 2» и «Дюна: Часть 2». Признак — то, что стоит ПЕРЕД цифрой
    (:data:`_TITLE_NUMBER_RE`): слово вроде ``Vol``/``Part``/«Часть» или просто точка с
    двоеточием, которыми каталог вводит подзаголовок.

    Обычный номер части при этом остаётся номером: «Тачки 3», «Моана 2», «Терминатор 2»
    заканчиваются буквой, а не показателем, и режутся как раньше.
    """
    match = re.search(r"^(?P<name>.+?)\s+(?P<index>\d{1,2})$", query.strip())
    if not match:
        return query.strip(), None
    name = match.group("name").strip()
    if _TITLE_NUMBER_RE.search(name):
        return query.strip(), None
    return name, int(match.group("index"))
