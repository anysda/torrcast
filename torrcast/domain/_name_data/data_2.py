# ruff: noqa: E501
"""Часть таблиц разбора имён; используют чистые правила домена."""

from __future__ import annotations

import re
from typing import Final

_RU_EXT_RE: Final = re.compile(
    "\\b(?:rus(?:sian)?|рус\\w*)\\s*\\(\\s*ext(?![^)]*\\bint\\b)[^)]*\\)", re.IGNORECASE
)
_RU_STUDIO_RE: Final = re.compile(
    "anilib(?:ria|erty)|ani-?dub|shiza|animevost|ani-?media|anistar|anifilm|animaunt|anirise|aniplague|aniomnia|persona\\s*99|kansai|ancord|jaskier|студийн\\w*\\s+банд\\w*|studio\\s*band|дядюшк\\w*\\s+шурик|кубик\\s+в\\s+кубе|lostfilm|newstudio|alexfilm|hdrezka|amazing\\s*dubbing",
    re.IGNORECASE,
)
_FOREIGN_LANG: Final = "(?:eng|english|англ\\w*|ita|ital\\w*|spa|esp|lat|pt-?br|por|fre|fra|fren\\w*|ger|deu|jap|jpn|japanese|kor|korean|chi|zho|chinese|ara|arabic|hin|tur|ukr|укр|kaz|каз|thai|tamil|malaysian|bahasa\\s+melayu|multi\\d*|dual)"
_FOREIGN_DUB_RE: Final = re.compile(
    f"\\b{_FOREIGN_LANG}[\\s._+-]*(?:audio|dubs?|dubbed|voice)\\b|\\bdubs?\\b\\s*[-–:]\\s*{_FOREIGN_LANG}\\b(?:\\s*[,+/]\\s*{_FOREIGN_LANG}\\b)*",
    re.IGNORECASE,
)
_NON_VIDEO_RE: Final = re.compile(
    "\\b(flac|mp3|ape|wav|lossless|vinyl|аудиокнига|audiobook|pdf|fb2|epub|djvu|mobi|rtf|azw3|cbz|cbr|repack|gog|steam-?rip|pc|рс|пк|x64|iso|portable|crack|ps[1-5]|psp|xbox|nintendo|wii|cinematic\\s+video)\\b",
    re.IGNORECASE,
)
_VIDEO_MARKER_RE: Final = re.compile(
    "\\b(2160p|1080p|720p|576p|480p|4k|uhd|bdrip|bdremux|remux|blu-?ray|web-?dl|web-?rip|webrip|hdrip|dvd\\d?|dvdrip|dvdscr|hdtv|hdtvrip|vhsrip|ntsc|pal|hevc|x26[45]|h\\.?26[45]|avc|s\\d{1,2}e\\d{1,3})\\b",
    re.IGNORECASE,
)
_COLLECTION_LATIN: Final = "collection"
_COLLECTION_RUSSIAN: Final = "кинотрилогия|трилогия|дилогия|квадрология|антология|коллекция"
_TITLE_CUT_RE: Final = re.compile(
    f"\\b(?:bd-?remux|bd-?rip|remux|blu-?ray|web-?dl\\w*|web-?rip|webrip|hdrip|dvd-?rip|dvd\\d?|hdtv\\w*|hdcam|telesync|dvdscr|satrip|iptv|2160p|1080p|720p|576p|480p|4k|uhd|hevc|x26[45]|h\\.?\\s?26[45]|avc|av1|s\\d{{1,2}}\\s?e\\d{{1,3}}|s\\d{{2}}|season|сезон|complete|\\d+\\s*(?:из|of)\\s*\\d+|серии|серия|выпуск|{_COLLECTION_LATIN})\\b|\\b(?:{_COLLECTION_RUSSIAN})\\b(?!\\s+[^\\W\\d_])",
    re.IGNORECASE,
)
_COLLECTION_CUT_RE: Final = re.compile(
    f"^(?:{_COLLECTION_LATIN}|{_COLLECTION_RUSSIAN})$", re.IGNORECASE
)
_ALTERNATIVE_PICTURE_RE: Final = re.compile(
    "\\bпароди[яи]\\b|\\bфанатск\\w*\\s+верси\\w*\\b|\\b(?:fan[ ._-]?edit)\\b|\\bсмешн(?:ой|ый)\\s+перевод\\b",
    re.IGNORECASE,
)
_ALTERNATIVE_TITLE_RE: Final = re.compile("\\(гоблин\\)", re.IGNORECASE)
_RU_CUT_WORDS: Final = frozenset(_COLLECTION_RUSSIAN.split("|"))
_TITLE_TAIL_RE: Final = re.compile(
    "(?:\\s*[-|]\\s*(?:aniliberty\\.top|anilibria\\w*|complete|extras?|full)\\s*$)+", re.IGNORECASE
)
_BRACKETS_RE: Final = re.compile("[\\[(][^\\[\\]()]*[\\])]")
_OPEN_BRACKET_RE: Final = re.compile("[\\[(]")
_PART_NUMBER_RE: Final = re.compile("^.+?[\\s,-]+(\\d{1,2}|[ivx]{1,4})(?=\\s*[:.]|\\s*$)", re.I)
_CHAPTER_RE: Final = re.compile("\\b(?:часть|part)$", re.IGNORECASE)
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
#: Слова, которыми выдача называет ФОРМУ картины: полный метр против сериала. Одна
#: выдача зовёт фильм «Gekijouban X», другая - голым «X», и до сих пор их разводило
#: ровно это слово: имена не совпадали, союза не было, и одна картина стояла в меню
#: двумя пунктами под двумя именами.
#:
#: Список закрытый нарочно, как `_KIND_MARKS` в :mod:`torrcast.domain.unmarked`. Слово формы
#: снимается и в СЕРЕДИНЕ имени - иначе «Naruto Movie 3: Guardians» не сойдётся с
#: «Naruto the Movie 3: Guardians», - а стрижка внутри имени тем и опасна, что за
#: закрытым списком она резала бы живое: «Унесённые призраками: фильм о фильме».
#: Многословные записи стоят тут ради своей длины: «cowboy-bebop-the-movie» без
#: `the-movie` остался бы «cowboy-bebop-the», и голое «Ковбой Бибоп» ему не тёзка.
_FORM_WORDS: Final = frozenset(
    {
        "gekijou-soushuuhen",
        "gekijouban",
        "gekijou",
        "the-movie",
        "movie",
        "film",
        "кинофильм",
        "фильм",
    }
)
#: Хвосты, которыми выдача называет ИЗДАНИЕ той же картины, а не другую работу. Одна
#: раздача зовётся «Врата Штейна», соседняя - «Врата Штейна: Полное издание», и меню
#: разводило их двумя пунктами: у настоящего девяносто одна раздача, у двойника одна.
#:
#: Список закрытый и снимается ТОЛЬКО с конца ключа, как `_FORM_WORDS` - закрытым
#: списком. Правило «выкинуть всё после точки» тут запрещено: рядом лежат хвосты, за
#: которыми стоит ДРУГАЯ работа с другим хронометражом, и склейка подсунула бы зрителю
#: не тот фильм: «Игра Престолов: Дополнительные материалы», «Властелин колец -
#: история создания», «Твин Пикс: Огонь, иди со мной - Пропавшие фрагменты»,
#: «Властелин Колец. Презентация с Каннского фестиваля», «Евангелион - дополнение».
#:
#: 🔴 «Расширенная версия» в список НЕ входит и войти не может, хотя выглядит роднёй
#: «Расширенного издания»: ею же переведено английское «Expanded», и так зовутся
#: документальные фильмы О картине - «Чужие: Расширенная версия / Aliens Expanded»
#: (2024), «Нечто. Расширенная версия / The Thing Expanded» (2026). Сняв этот хвост,
#: склейка увела бы документалку в пул самой картины. Слово «издание» такой двусмыслицы
#: не знает: издание - это выпуск носителя, а не отдельная работа.
_EDITION_TAILS: Final = frozenset(
    {
        # Торговые издания одного и того же носителя: полнота комплекта, сувенирность
        # и добавленные минуты - свойство РАЗДАЧИ, выбирают её, а не пункт меню.
        "полное-издание",
        "коллекционное-издание",
        "расширенное-издание",
        # Другой монтаж той же картины. Решение продукта (TC-910): склеивать, выбор
        # монтажа - дело отбора раздачи. Буква «ё» сюда не доезжает: slugify её сводит.
        "режиссерская-версия",
    }
)
_YEAR_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile("[(\\[]\\s*((?:19|20)\\d{2})(?:\\s*[-/]\\s*(?:19|20)\\d{2})*\\s*[,)\\]]"),
    re.compile("(?:^|[/|,]\\s*)((?:19|20)\\d{2})(?:\\s*-\\s*(?:19|20)\\d{2})?\\s*(?=[/|,]|$)"),
    re.compile("(?<=[\\s.])((?:19|20)\\d{2})(?=[\\s.])"),
)
_MERGED_TAIL: Final = "(?:[_exх]\\d{1,3})?"
_SEASON_EPISODE_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        # Номер серии до четырёх знаков: у длинных сериалов счёт идёт на тысячи
        # («S01E1171»), и обрезать его тремя значит не увидеть сериал вовсе.
        "\\bs\\s*(?P<season>\\d{1,2})\\s*[.\\-_ ]?\\s*e\\s*(?P<episode>\\d{1,4})"
        + _MERGED_TAIL
        + "\\b",
        re.IGNORECASE,
    ),
    re.compile(
        "\\b(?P<season>\\d{1,2})\\s*[xх]\\s*(?P<episode>\\d{1,4})" + _MERGED_TAIL + "\\b",
        re.IGNORECASE,
    ),
    re.compile("(?P<season>\\d{1,2})\\s*сезон\\D{0,14}?(?P<episode>\\d{1,3})\\s*сери\\w*", re.I),
    re.compile("(?P<episode>\\d{1,3})\\s*сери\\D{0,14}?(?P<season>\\d{1,2})\\s*сезон\\w*", re.I),
)
_SEASON_ONLY_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile("\\bs\\s?(?P<season>\\d{1,2})\\b(?!\\s?e)", re.IGNORECASE),
    re.compile("(?P<season>\\d{1,2})[-\\s]*(?:й\\s*)?сезон", re.IGNORECASE),
    re.compile("season\\s*(?P<season>\\d{1,2})", re.IGNORECASE),
)
_SEASON_SPAN_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile("\\bs\\s?(\\d{1,2})\\s*-\\s*s?\\s?(\\d{1,2})\\b", re.IGNORECASE),
    re.compile("\\b(\\d{1,2})\\s*-\\s*(\\d{1,2})\\s*(?:сезон\\w*|seasons?)\\b", re.IGNORECASE),
    re.compile(
        "(?<!\\d)(?<!\\d\\s)\\b(?:сезон\\w*|seasons?)\\s*:\\s*(\\d{1,2})\\s*-\\s*(\\d{1,2})(?:\\s*(?:из|of)\\s*\\d{1,2})?\\b",
        re.IGNORECASE,
    ),
)
_EPISODE_BRACKET_RE: Final = re.compile(
    # Скобочная линейка серий: «[01-12]», «[1-26]», «(27-40)», «[01-12TV全集+OVA]».
    # Начало - не четыре знака, поэтому скобочный диапазон лет («[2001-2011]»)
    # сюда не попадает; за концом разрешена пометка сборника в тех же скобках.
    # Началу без ведущего нуля нужен конец из двух цифр: «[1-4]» - это нумерация
    # частей франшизы, сборник фильмов, и сериями он не читается.
    "[\\[(]\\s*(?:[eеэ]p?\\.?\\s*)?"
    "(?P<start>0\\d{1,2}|\\d{3}|\\d{1,3}(?=\\s*-\\s*\\d{2}))"
    "\\s*-\\s*(?P<end>\\d{1,3})(?!\\d)[^\\[\\]()]*[\\])]"
)
