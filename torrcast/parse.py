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

import re
import statistics
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol

__all__ = [
    "THIN_POOL",
    "VIDEO_EXT",
    "Episode",
    "EpisodeFile",
    "Picture",
    "Release",
    "alt_query",
    "cluster",
    "franchise_key",
    "franchises",
    "map_episodes",
    "parse_episode",
    "parse_release_name",
    "part_number",
    "pick_franchise",
    "slugify",
    "split_episode",
    "split_franchise_index",
    "transliterate",
]

Kind = Literal["movie", "tv", "other"]

_CYRILLIC: Final = re.compile(r"[а-яё]", re.IGNORECASE)
_UKRAINIAN: Final = re.compile(r"[іїєґ]", re.IGNORECASE)
_LATIN: Final = re.compile(r"[a-z]", re.IGNORECASE)

_QUALITY_RE: Final = re.compile(r"\b(2160p|1080p|720p|576p|480p|360p|4k|uhd)\b", re.IGNORECASE)
_HEVC_RE: Final = re.compile(r"\b(hevc|h\.?\s?265|x265)\b", re.IGNORECASE)
_H264_RE: Final = re.compile(r"\b(avc|h\.?\s?264|x264)\b", re.IGNORECASE)
#: MPEG-4 Part 2 (XviD/DivX и родня). Читается ПОСЛЕ H.264: «MPEG-4 AVC» — это H.264,
#: и порядок в :func:`_parse_codec` разводит их сам, без хитрых заглядываний вперёд.
_MPEG4_RE: Final = re.compile(
    r"\b(xvid|divx|dx50|div3|3ivx|ms-?mpeg-?4|mpeg-?4|mp4v)\b", re.IGNORECASE
)
_AV1_RE: Final = re.compile(r"\bav1\b", re.IGNORECASE)
_HDR_RE: Final = re.compile(r"\b(hdr10\+?|hdr|dolby\s*vision|dv)\b", re.IGNORECASE)
#: Контейнер .avi в имени. Внутри .avi H.264 бывает, но на живой выдаче (36 раздач,
#: у которых удалось достать .torrent и заглянуть в имена файлов) все восемь .avi
#: оказались SD-рипами MPEG-4 — ни одного исключения.
_AVI_RE: Final = re.compile(r"\.avi\b", re.IGNORECASE)

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
    (r"дубляж|дублир|\bдб\b|\bdub\b", "Дубляж"),
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

#: Не-видео: музыка, книги, игры. Срабатывает только при отсутствии видео-маркеров.
_NON_VIDEO_RE: Final = re.compile(
    r"\b(flac|mp3|ape|wav|lossless|vinyl|аудиокнига|audiobook|"
    r"pdf|fb2|epub|djvu|mobi|rtf|azw3|"
    r"repack|gog|steam-?rip|pc|x64|iso|portable|crack)\b",
    re.IGNORECASE,
)
_VIDEO_MARKER_RE: Final = re.compile(
    r"\b(2160p|1080p|720p|576p|480p|4k|uhd|bdrip|bdremux|remux|blu-?ray|web-?dl|"
    r"web-?rip|webrip|hdrip|dvd\d?|dvdrip|dvdscr|hdtv|hdtvrip|vhsrip|ntsc|pal|"
    r"hevc|x26[45]|h\.?26[45]|avc|s\d{1,2}e\d{1,3})\b",
    re.IGNORECASE,
)

#: Всё, что после этих токенов, к названию не относится.
_TITLE_CUT_RE: Final = re.compile(
    r"\b(?:bd-?remux|bd-?rip|remux|blu-?ray|web-?dl\w*|web-?rip|webrip|hdrip|"
    r"dvd-?rip|dvd\d?|hdtv\w*|hdcam|telesync|dvdscr|satrip|iptv|"
    r"2160p|1080p|720p|576p|480p|4k|uhd|hevc|x26[45]|h\.?\s?26[45]|avc|av1|"
    r"s\d{1,2}\s?e\d{1,3}|s\d{2}|season|сезон|complete|\d+\s*(?:из|of)\s*\d+|"
    r"серии|серия|выпуск|трилогия|дилогия|квадрология|антология|коллекция|collection)\b",
    re.IGNORECASE,
)
#: Мусорный хвост названия: релиз-группы и слова-пустышки.
_TITLE_TAIL_RE: Final = re.compile(
    r"(?:\s*[-|]\s*(?:aniliberty\.top|anilibria\w*|complete|extras?|full)\s*$)+", re.IGNORECASE
)
_BRACKETS_RE: Final = re.compile(r"[\[(][^\[\]()]*[\])]")
_OPEN_BRACKET_RE: Final = re.compile(r"[\[(]")
#: Явный номер части в самом названии: «Тачки 3», «Форсаж - 8», «Терминатор II: …».
_PART_NUMBER_RE: Final = re.compile(r"^.+?[\s,-]+(\d{1,2}|[ivx]{1,4})(?=\s*[:.]|\s*$)", re.I)
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
    re.compile(r"[(\[]\s*((?:19|20)\d{2})(?:\s*-\s*(?:19|20)\d{2})?\s*[,)\]]"),
    re.compile(r"(?:^|[/|,]\s*)((?:19|20)\d{2})(?:\s*-\s*(?:19|20)\d{2})?\s*(?=[/|,]|$)"),
    re.compile(r"(?<=[\s.])((?:19|20)\d{2})(?=[\s.])"),
)

_SEASON_EPISODE_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bs\s*(?P<season>\d{1,2})\s*[.\-_ ]?\s*e\s*(?P<episode>\d{1,3})\b", re.IGNORECASE),
    re.compile(r"\b(?P<season>\d{1,2})\s*[xх]\s*(?P<episode>\d{1,3})\b", re.IGNORECASE),
    # Хвост слова забираем целиком: «5 серия» вырезается из запроса без остатка «…я».
    re.compile(r"(?P<season>\d{1,2})\s*сезон\D{0,14}?(?P<episode>\d{1,3})\s*сери\w*", re.I),
    re.compile(r"(?P<episode>\d{1,3})\s*сери\D{0,14}?(?P<season>\d{1,2})\s*сезон\w*", re.I),
)
_SEASON_ONLY_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bs\s?(?P<season>\d{1,2})\b(?!\s?e)", re.IGNORECASE),
    re.compile(r"(?P<season>\d{1,2})[-\s]*(?:й\s*)?сезон", re.IGNORECASE),
    re.compile(r"season\s*(?P<season>\d{1,2})", re.IGNORECASE),
)
#: Диапазон сезонов в имени раздачи: ``[S01-06]``, ``S01-S06``, «1-6 сезоны».
_SEASON_SPAN_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bs\s?(\d{1,2})\s*-\s*s?\s?(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s*-\s*(\d{1,2})\s*(?:сезон\w*|seasons?)\b", re.IGNORECASE),
)
#: Серии, лежащие ВНУТРИ раздачи, по её имени. Порядок обязателен: сначала диапазон
#: («1-5 из 220» = серии 1…5), потом счёт («220 of 220» = все 220, то есть 1…220).
#: Прочитай их наоборот - и полный сезон превратился бы в одну серию, а огрызок в пак.
#: Числа ограничены тремя цифрами и обрамлены стражами ``(?<!\d)/(?!\d)``: без них
#: «(2005-2020)» в имени читалось бы как диапазон серий.
_EPISODE_SPAN_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"(?<!\d)(?P<start>\d{1,3})\s*-\s*[eеэ]?\s*(?P<end>\d{1,3})(?!\d)\s*(?:из|of)\s*\d{1,3}",
        re.IGNORECASE,
    ),
    re.compile(r"(?<!\d)(?P<start>\d{1,3})\s*-\s*(?P<end>\d{1,3})(?!\d)\s*сери", re.IGNORECASE),
    re.compile(r"сери[ияй]\s*(?P<start>\d{1,3})\s*-\s*(?P<end>\d{1,3})(?!\d)", re.IGNORECASE),
    # Без «из/of»: ``S01E01-08``, ``E12-24``. Буква ``e`` обязательна - голое «1-8»
    # в имени раздачи чаще про части названия, чем про серии.
    re.compile(r"[eеэ]\s*(?P<start>\d{1,3})\s*-\s*[eеэ]?\s*(?P<end>\d{1,3})(?!\d)", re.IGNORECASE),
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
#: Расширения видео: всё прочее в раздаче — субтитры, обложки и мусор.
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

#: Токены кодека: цифры в них к сериям отношения не имеют. Вырезаются только в разборе
#: сериальности (:func:`_parse_series`) — сам кодек читается отдельно и раньше.
_CODEC_TOKEN_RE: Final = re.compile(
    r"\b[xх]\s?26[456]\b|\bh\.?\s?26[456]\b|\bavc\b|\bhevc\b|\bav1\b|\bvp9\b|\bdiv[x]\b",
    re.IGNORECASE,
)

#: Сериальность без номера сезона: «12 из 24», «E12 of 12», «[ТВ-2]».
#: Голое ``episode``/``tv`` сюда не годится — «Star Wars Episode I» это фильм.
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
    year: int | None = None
    quality: str | None = None
    codec: str | None = None
    source: str | None = None
    hdr: bool = False
    voices: tuple[str, ...] = ()
    season: int | None = None
    episode: int | None = None
    #: Сезоны пака целиком: ``[S01-06]`` → (1…6). Пусто — сезон один или не назван.
    seasons: tuple[int, ...] = ()
    #: Серии, которые лежат ВНУТРИ раздачи, по её имени: ``[S01E01-08 of 220]`` → (1…8),
    #: ``[E220 of 220]`` → (1…220). Пусто — имя о серияx молчит, и решат файлы.
    episodes: tuple[int, ...] = ()
    size: int = 0
    seeders: int = 0
    magnet: str = ""
    indexer: str = ""
    kind: Kind = "movie"

    @property
    def is_hevc(self) -> bool:
        """HEVC показываем с пометкой ⚠ и никогда не берём по умолчанию."""
        return self.codec == "HEVC"

    @property
    def height(self) -> int:
        """Высота кадра из качества; 0 — качество в имени не указано."""
        digits = (self.quality or "").rstrip("p")
        return int(digits) if digits.isdigit() else 0

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
    releases: list[Release] = field(default_factory=list)

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
    def seeders(self) -> int:
        return max((r.seeders for r in self.releases), default=0)

    @property
    def best_release(self) -> Release | None:
        """Дефолт меню: самый обсиженный среди релизов первого сорта (H.264, ≥720p);
        нет таких — просто самый обсиженный.
        """
        if not self.releases:
            return None
        return sorted(self.releases, key=lambda r: (not r.prime, -r.seeders, -r.size))[0]


@dataclass(frozen=True, slots=True)
class Episode:
    season: int
    episode: int

    def __str__(self) -> str:
        return f"s{self.season}e{self.episode}"


def slugify(text: str) -> str:
    """Название → ключ состояния: нижний регистр, дефисы, без мусора; кириллица
    сохраняется, ключи русские (``movie:матрица:1999``).
    """
    normalized = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    return re.sub(r"[^0-9a-zа-я]+", "-", normalized).strip("-")


def franchise_key(title: str) -> str:
    """Каноническое имя франшизы: «Матрица: Перезагрузка» и «Тачки 3» → одна серия.
    Режем подзаголовок после двоеточия и хвостовой номер части — именно они
    отличают фильмы внутри франшизы.
    """
    base = re.split(r"\s*:\s*|\.\s+", title.strip(), maxsplit=1)[0]
    # Хвост «3», «- 8», «II», а также диапазон «1-4» у сборников.
    base = re.sub(
        r"[\s,-]+(?:\d{1,2}(?:\s*[-,]\s*\d{1,2})*|[ivx]{1,4})\s*$", "", base, flags=re.IGNORECASE
    )
    return slugify(base.rstrip(" -")) or slugify(title)


def part_number(title: str) -> int | None:
    """Явный номер части в названии: «Тачки 3» → 3, «Терминатор II» → 2, иначе None."""
    match = _PART_NUMBER_RE.match(title.strip())
    if not match:
        return None
    if re.search(r"\d\s*[-,]\s*$", title[: match.start(1)]):
        return None  # «Форсаж 1-4», «Матрица 1,2,3» — это диапазон, а не номер части
    token = match.group(1).lower()
    return int(token) if token.isdigit() else _ROMAN.get(token)


#: Ниже этого числа раздач пул картины считается тощим. Число не с потолка: на живом
#: каталоге у картины, найденной целиком, раздач десятки («Матрица» 59, «Бешеные псы» 69,
#: «Клан Сопрано» 35), а у картины, до которой русский запрос дотянулся лишь краем, -
#: единицы («Птицы» 1, «Дилижанс» 1, «Дедвуд» 4, «Психо» 10). Между этими кучами широкий
#: провал, и порог стоит в нём: на полной выдаче второй заход не случается вовсе.
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


def transliterate(text: str) -> str:
    """Русское название латиницей; латинские куски и цифры остаются как есть."""
    lowered = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", "".join(_TRANSLIT.get(ch, ch) for ch in lowered)).strip()


def alt_query(query: str, releases: Iterable[Release]) -> str:
    """Чем ещё называется то, что спросили по-русски: запрос для второго захода.

    Зачем он вообще. Индексеры ищут по ИМЕНИ раздачи, а не по картине: половина
    каталога подписана только латиницей («Psycho.1960.1080p»), и русский запрос до неё
    не достаёт - человеку пришлось бы догадаться набрать «Psycho». Само название при
    этом лежит в той же выдаче: раздачи вида «Психо / Psycho (1960)» её и приносят,
    надо лишь прочитать у них оригинал и переспросить им.

    Оригинал из выдачи точнее транслита («Психо» → ``Psycho``, а не ``psikho``), поэтому
    он первый. Транслит - запасной путь для случая, когда выдачи нет вовсе и читать
    нечего; он выручает русское кино, которое за рубежом так и подписывают (``Brat``).
    Пустая строка - добирать нечем: запрос и так на латинице.
    """
    if not _CYRILLIC.search(query):
        return ""
    wanted = slugify(query)
    names = Counter(
        original.strip()
        for release in releases
        if (original := release.original) and _akin(wanted, slugify(release.title))
    )
    for name, _count in names.most_common():
        if name and not _CYRILLIC.search(name) and slugify(name) != wanted:
            return name
    return transliterate(query)


def _akin(wanted: str, slug: str) -> bool:
    """Один ли это фильм по slug: точное совпадение или вхождение в любую сторону
    («психо» ↔ «психо-2», «сияние» ↔ «сияние»).
    """
    return bool(wanted) and bool(slug) and (wanted in slug or slug in wanted)


def split_franchise_index(query: str) -> tuple[str, int | None]:
    """Отделить хвостовой номер франшизы: ``«матрица 2»`` → ``("матрица", 2)``. Номер —
    позиция в отсортированной по году франшизе, а не часть названия;
    год (четыре цифры) номером не считается.
    """
    match = re.search(r"^(?P<name>.+?)\s+(?P<index>\d{1,2})$", query.strip())
    if not match:
        return query.strip(), None
    return match.group("name").strip(), int(match.group("index"))


def parse_episode(text: str) -> Episode | None:
    """Вытащить ``sNeM`` из строки: ``s02e05``, ``2x5``, «2 сезон 5 серия»."""
    for pattern in _SEASON_EPISODE_RES:
        match = pattern.search(text)
        if match:
            return Episode(int(match.group("season")), int(match.group("episode")))
    return None


def split_episode(text: str) -> tuple[str, Episode | None]:
    """Отделить от запроса указание серии: ``«киберпанк 2x5»`` → ``("киберпанк", s2e5)``.
    Хвост вырезается целиком — «2 сезон 5 серия» тоже, иначе в поиск уедет «киберпанк 2».
    """
    for pattern in _SEASON_EPISODE_RES:
        match = pattern.search(text)
        if match:
            rest = f"{text[: match.start()]} {text[match.end() :]}"
            title = re.sub(r"\s+", " ", rest).strip(" .,-—:")
            return title, Episode(int(match.group("season")), int(match.group("episode")))
    return text.strip(), None


class FileLike(Protocol):
    """Файл раздачи глазами парсера — ровно то, что отдаёт TorrServer."""

    @property
    def index(self) -> int: ...
    @property
    def name(self) -> str: ...
    @property
    def size(self) -> int: ...


@dataclass(frozen=True, slots=True)
class EpisodeFile:
    """Файл раздачи, опознанный как серия: список серий = файлы раздачи."""

    index: int
    season: int
    episode: int
    name: str
    size: int = 0

    @property
    def at(self) -> Episode:
        return Episode(self.season, self.episode)


def map_episodes(files: Sequence[FileLike], season_hint: int | None = None) -> list[EpisodeFile]:
    """Файлы раздачи → серии. Пак это или один сезон — решают ФАЙЛЫ, а не имя
    раздачи: сколько сезонов нашлось в путях, столько в ответе и будет.

    Читаем весь список одним способом и проверяем его на связность: сколько файлов
    разобрано, столько и должно выйти разных ``sNeM``. Иначе ``Naruto.Shippuuden.001.
    IPTVRip.2x2.XviD.avi`` (2x2 — телеканал-рипер, а не «2 сезон 2 серия») дал бы всем
    318 файлам один и тот же номер. Не сошлось — пробуем следующий способ:
    полный ``sNeM`` → номер серии без сезона → голый номер (аниме) → порядок файлов.
    """
    videos = [f for f in files if f.name.lower().endswith(VIDEO_EXT)]
    videos = [f for f in videos if not _JUNK_RE.search(f.name)]
    videos = _drop_small(videos)
    for read in (_read_sne, _read_episode_only, _read_bare):
        found = _collect(videos, read, season_hint)
        if found:
            return found
    return _collect(videos, _read_order, season_hint, strict=False)


def _collect(
    videos: Sequence[FileLike],
    read: Callable[[str, int], tuple[int | None, int] | None],
    hint: int | None,
    strict: bool = True,
) -> list[EpisodeFile]:
    """Применить способ чтения ко всем файлам и проверить результат на связность."""
    picked: dict[tuple[int, int], FileLike] = {}
    matched = 0
    for order, item in enumerate(videos, start=1):
        found = read(_base(item.name), order)
        if found is None:
            continue
        matched += 1
        season, episode = found
        if season is None:
            season = _season_of(item.name, hint)
        was = picked.get((season, episode))
        if was is None or item.size > was.size:  # тот же номер дважды — берём файл крупнее
            picked[(season, episode)] = item
    # Разнобой: номера повторяются (значит, читали не то) или разобралась горстка файлов.
    if strict and (not picked or len(picked) * 10 < matched * 9 or matched * 2 < len(videos)):
        return []
    return sorted(
        (EpisodeFile(f.index, s, e, _base(f.name), f.size) for (s, e), f in picked.items()),
        key=lambda f: (f.season, f.episode),
    )


def _read_sne(name: str, _order: int) -> tuple[int | None, int] | None:
    """Полный ``sNeM``: ``S01E01``, ``S01.E01``, ``01x01``, «2 сезон 5 серия»."""
    found = parse_episode(name)
    return (found.season, found.episode) if found else None


def _read_episode_only(name: str, _order: int) -> tuple[int | None, int] | None:
    """Номер серии есть, сезона в имени файла нет: ``E05``, «05 из 24», «5 серия»."""
    for pattern in _EPISODE_ONLY_RES:
        match = pattern.search(name)
        if match:
            return None, int(match.group("episode"))
    return None


def _read_bare(name: str, _order: int) -> tuple[int | None, int] | None:
    """Голый номер серии — норма для аниме: ``[Group] Title 05 [BDRip]``, ``Naruto - 216``.
    Скобки и технические токены (``1920x1080``, ``10bit``, год) выбрасываются, из
    оставшихся чисто числовых токенов берётся последний.
    """
    bare = _BRACKETS_RE.sub(" ", name)
    tokens = [t for t in re.split(r"[\s._\-]+", bare) if t and not _TECH_TOKEN_RE.match(t)]
    numbers = [int(t) for t in tokens if t.isdigit() and len(t) <= 3]
    return (None, numbers[-1]) if numbers else None


def _read_order(_name: str, order: int) -> tuple[int | None, int] | None:
    """Последняя надежда: в именах номеров нет вовсе — нумеруем по порядку файлов."""
    return None, order


def _season_of(path: str, hint: int | None) -> int:
    """Сезон файла: из каталога (``Season 3/``, ``S03/``, «3 сезон»), иначе из имени
    раздачи, иначе первый — односезонные аниме-раздачи о сезоне молчат вовсе.
    """
    folder = path.rsplit("/", 1)[0] if "/" in path else ""
    for pattern in _SEASON_ONLY_RES:
        match = pattern.search(folder)
        if match:
            return int(match.group("season"))
    return hint or 1


def _drop_small(videos: list[FileLike]) -> list[FileLike]:
    """Выбросить огрызки: сэмпл рядом с сериями весит проценты от их размера."""
    sizes = [f.size for f in videos if f.size > 0]
    if len(sizes) < 3:
        return videos
    edge = statistics.median(sizes) * _SMALL_RATIO
    return [f for f in videos if f.size >= edge or f.size == 0]


def _base(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def parse_release_name(name: str) -> Release:
    """Разобрать имя раздачи в структуру (форматы — в докстринге модуля)."""
    text = _normalize(name)
    year, span = _find_year(text)
    title, original = _split_titles(_title_zone(text, span))

    quality_match = _QUALITY_RE.search(text)
    quality = _normalize_quality(quality_match.group(1)) if quality_match else None

    season, episode, seasons, episodes, series = _parse_series(text)
    kind: Kind = "other" if _is_non_video(text) else ("tv" if series else "movie")

    return Release(
        raw_name=name,
        title=title,
        original=original,
        year=year,
        quality=quality,
        codec=_parse_codec(text),
        source=_parse_source(text),
        hdr=bool(_HDR_RE.search(text)),
        voices=_parse_voices(text),
        season=season,
        episode=episode,
        seasons=seasons,
        episodes=episodes,
        kind=kind,
    )


def cluster(releases: list[Release]) -> list[Picture]:
    """Сгруппировать релизы в картины; порядок = хронология франшизы.
    Кросс-язычность: если хоть где-то встретилось ``Тачки 3 / Cars 3``, то чисто
    латинский релиз ``Cars 3`` попадёт в тот же кластер, что и русский.
    """
    aliases: dict[str, str] = {}
    for release in releases:
        if release.original and _CYRILLIC.search(release.title):
            aliases.setdefault(slugify(release.original), slugify(release.title))

    # Ключ кластера — русский slug; при совпадении оригинала и года варианты
    # перевода («Матрица 2: Перезагрузка» и «Матрица: Перезагрузка») сливаются.
    canon: dict[tuple[Kind, str, int | None], tuple[Kind, str, int | None]] = {}
    buckets: dict[tuple[Kind, str, int | None], list[Release]] = {}
    for release in releases:
        slug = release.slug if release.original else aliases.get(release.slug, release.slug)
        key = (release.kind, slug, release.year)
        if release.original:
            by_orig = (release.kind, slugify(release.original), release.year)
            key = canon.setdefault(by_orig, key)
        buckets.setdefault(key, []).append(release)

    pictures: list[Picture] = []
    for (kind, _, year), group in buckets.items():
        titles = Counter(r.title for r in group if _CYRILLIC.search(r.title))
        title = (titles or Counter(r.title for r in group)).most_common(1)[0][0]
        originals = Counter(r.original for r in group if r.original)
        # Номер части часто есть лишь в части переводов («Матрица 2: Перезагрузка»)
        # — забираем его на всю картину, он точнее года при двух фильмах за год.
        parts = Counter(n for r in group if (n := part_number(r.title)) is not None)
        pictures.append(
            Picture(
                title=title,
                year=year,
                kind=kind,
                original=originals.most_common(1)[0][0] if originals else None,
                part=parts.most_common(1)[0][0] if parts else None,
                releases=group,
            )
        )
    return sorted(pictures, key=lambda p: (p.year is None, p.year or 0, p.title))


def franchises(pictures: list[Picture]) -> dict[str, list[Picture]]:
    """Картины → франшизы: общий канонический ключ, значение отсортировано по году.
    Два фильма за один год («Перезагрузка» и «Революция», обе 2003) разводит явный
    номер части; без него вперёд идёт картина с бо́льшим числом раздач — основной
    фильм, а не спин-офф или «киноляпы».
    """
    grouped: dict[str, list[Picture]] = {}
    for picture in pictures:
        grouped.setdefault(picture.franchise, []).append(picture)
    for items in grouped.values():
        items.sort(key=lambda p: (p.year is None, p.year or 0, p.part or 99, -len(p.releases)))
    return grouped


def pick_franchise(query: str, pictures: list[Picture]) -> list[Picture]:
    """``«матрица 2»`` → [«Матрица: Перезагрузка»]; без номера — вся франшиза. Ищем по
    каноническому ключу (русскому или оригинальному), затем по вхождению подстроки;
    номер — индекс в хронологии, а не часть названия.
    """
    groups = franchises(pictures)
    aliases = {
        franchise_key(p.original): key for key, items in groups.items() for p in items if p.original
    }

    def lookup(name: str) -> str | None:
        wanted = slugify(name)
        if not wanted:
            return None
        if wanted in groups:
            return wanted
        if wanted in aliases:
            return aliases[wanted]
        if hits := [k for k in groups if wanted in k]:
            return min(hits, key=len)
        # Запрос длиннее канона: «киберпанк бегущие по краю» — это франшиза «киберпанк»
        # (подзаголовок после двоеточия в ключ не входит). Берём самое длинное совпадение.
        hits = [k for k in groups if k and k in wanted]
        return max(hits, key=len) if hits else None

    name, index = split_franchise_index(query)
    key = lookup(name)
    if key is None:  # номер оказался частью названия: «пила 8», «форсаж 6»
        key, index = lookup(query), None
    if key is None:
        return []

    items = _both_languages(groups, aliases, key)
    if index is None:
        return items
    # Явный номер части сильнее позиции: «тачки 2» → «Тачки 2», а не спин-офф.
    explicit = [p for p in items if p.part == index]
    if explicit:
        return [max(explicit, key=lambda p: len(p.releases))]
    return [items[index - 1]] if 1 <= index <= len(items) else []


def _both_languages(
    groups: dict[str, list[Picture]], aliases: dict[str, str], key: str
) -> list[Picture]:
    """Франшиза целиком, когда её половина названа по-русски, а половина — латиницей.

    «Моана» на Knaben живёт двумя кучками: первая часть подписана только ``Moana``,
    вторая — ``Моана 2 / Moana 2``. Ключи франшиз у них разные (``moana`` и ``моана``),
    и запрос ``cast moana`` показывал бы только первую часть, а ``cast моана`` — только
    вторую. Псевдоним по оригинальному названию у нас уже посчитан — этого хватает,
    чтобы показать человеку всю франшизу, не трогая саму кластеризацию.
    """
    items = list(groups[key])
    # Псевдоним считается от оригинального названия к русскому, а спросить могут любым:
    # ``cast moana`` и ``cast моана`` обязаны показать одну и ту же франшизу.
    twins = {aliases.get(key, "")} | {a for a, target in aliases.items() if target == key}
    seen = {id(p) for p in items}
    for twin in twins:
        if not twin or twin == key:
            continue
        # ⚠️ В `seen` уходят только новички: пересчёт по всему списку стоил бы прохода на
        # каждого близнеца, то есть квадрата по числу картин на ровном месте.
        fresh = [p for p in groups.get(twin, []) if id(p) not in seen]
        items += fresh
        seen |= {id(p) for p in fresh}
    items.sort(key=lambda p: (p.year is None, p.year or 0, p.part or 99, -len(p.releases)))
    return items


def _normalize(name: str) -> str:
    text = unicodedata.normalize("NFKC", name).replace("\xa0", " ")
    text = text.replace("–", "-").replace("—", "-").replace("‐", "-")
    text = re.sub(r"(\d{3,4})\s*р\b", r"\1p", text)  # 720р (кириллица) → 720p
    return re.sub(r"\s+", " ", text).strip()


def _find_year(text: str) -> tuple[int | None, tuple[int, int] | None]:
    for pattern in _YEAR_PATTERNS:
        match = pattern.search(text)
        if match:
            return int(match.group(1)), match.span()
    return None, None


def _title_zone(text: str, span: tuple[int, int] | None) -> str:
    """Отрезать от имени кусок, в котором лежат названия."""
    zone = text[: span[0]] if span else text
    # Скобки убираем ПЕРВЫМИ: иначе «сезон» внутри «(5 сезон: 1-3 серии из 3)»
    # обрежет строку раньше оригинального названия, которое идёт после скобки.
    zone = _BRACKETS_RE.sub(" ", zone)  # (Режиссёр), [S01], (IMAX Edition), [Group]
    cut = _TITLE_CUT_RE.search(zone)
    if cut:
        zone = zone[: cut.start()]
    zone = _OPEN_BRACKET_RE.split(zone)[0]  # обрезали внутри скобки: «Bleach … [»
    # Отдельного правила для «от <релиз-группа>» нет и быть не должно: «от» —
    # обычный предлог («Человек-паук: Вдали от дома»), а хвост с группой и так
    # остаётся за техническим токеном, по которому строка уже обрезана.
    if zone.count(".") >= 2 and zone.count(" ") <= 1:  # scene-имя через точки
        zone = zone.replace(".", " ")
    zone = _TITLE_TAIL_RE.sub("", zone)
    return zone.strip(" .-_|,:;/")


def _split_titles(zone: str) -> tuple[str, str | None]:
    """``«Матрица / The Matrix»`` → русское и оригинальное название."""
    parts = [p.strip(" .-_|,:;") for p in re.split(r"[/|]", zone)]
    parts = [p for p in parts if len(p) > 1 and not _TAG_ONLY_RE.match(p)]
    if not parts:
        return zone.strip() or "?", None

    russian = next((p for p in parts if _CYRILLIC.search(p) and not _UKRAINIAN.search(p)), None)
    latin = next((p for p in parts if _LATIN.search(p) and not _CYRILLIC.search(p)), None)
    if russian is None:
        return latin or parts[0], None
    return russian, latin


def _parse_codec(text: str) -> str | None:
    """Кодек из имени. ⚠️ H.264 проверяется раньше MPEG-4: «MPEG-4 AVC» — это H.264,
    так пишут на rutracker про BDRip-AVC, и без этого порядка годный релиз уехал бы
    в старьё.
    """
    if _HEVC_RE.search(text):
        return "HEVC"
    if _H264_RE.search(text):
        return "H.264"
    if _MPEG4_RE.search(text):
        return "MPEG-4"
    return "AV1" if _AV1_RE.search(text) else None


def _parse_source(text: str) -> str | None:
    for pattern, label in _SOURCES:
        if re.search(pattern, text, re.IGNORECASE):
            return label
    return None


def _parse_voices(text: str) -> tuple[str, ...]:
    """Собрать маркеры озвучки в порядке приоритета, без повторов."""
    found: list[str] = []
    for pattern, label in _VOICES:
        if re.search(pattern, text, re.IGNORECASE) and label not in found:
            found.append(label)
    for segment in re.split(r"[|/]", text)[1:]:  # хвост rutor/megapeer: «| D, P, A»
        if not _TAG_ONLY_RE.match(segment):
            continue
        for code in re.findall(r"[DPAL]2?", segment):
            label = _TAG_VOICES.get(code) or _TAG_VOICES[code[0]]
            if label not in found:
                found.append(label)
    order = {label: i for i, (_, label) in enumerate(_VOICES)}
    return tuple(sorted(found, key=lambda v: order.get(v, 99)))


def _parse_series(
    text: str,
) -> tuple[int | None, int | None, tuple[int, ...], tuple[int, ...], bool]:
    """Сезон, серия, сезоны пака, серии пака и признак сериальности.

    ⚠️ Перед разбором из имени вырезаются токены кодека (:data:`_CODEC_TOKEN_RE`). Иначе
    ``x264`` рядом с любой цифрой читается как ``NxM``: «Moana 2 2024 … DDP5 1 x264» —
    это «5.1» плюс кодек, а разбор видел «1 x264» и объявлял полнометражку сериалом
    s1e264. Кодек о сериях не говорит ничего, поэтому вырезать его здесь безопасно —
    а весь остальной парсер остаётся как был.
    """
    text = _CODEC_TOKEN_RE.sub(" ", text)
    seasons = _season_span(text)
    episodes = _episode_span(text)
    if seasons:
        # Пак сезонов: серии внутри него нумеруются по-своему в каждом сезоне, и
        # диапазон из имени («S01-15 + Special») к ним отношения не имеет.
        return seasons[0], None, seasons, (), True
    found = parse_episode(text)
    if found is not None:
        # «S2E1-8 of 8» — это пак сезона, а не первая серия.
        pack = re.search(r"[eхx]\s*\d{1,3}\s*-\s*\d{1,3}", text, re.IGNORECASE)
        return found.season, None if pack else found.episode, (), episodes, True
    for pattern in _SEASON_ONLY_RES:
        match = pattern.search(text)
        if match:
            return int(match.group("season")), None, (), episodes, True
    return None, None, (), episodes, bool(_SERIES_HINT_RE.search(text))


def _episode_span(text: str) -> tuple[int, ...]:
    """Серии внутри раздачи по имени: «1-5 из 220» → (1…5), «220 of 220» → (1…220).

    Пусто — имя о серияx молчит. Диапазон читается раньше счёта (:data:`_EPISODE_SPAN_RES`
    против :data:`_EPISODE_COUNT_RE`), иначе «1-5 из 220» дало бы «серии 1…1»: «5 из 220»
    прочиталось бы как счёт. Вывернутые и бессмысленные границы («8-1», «0-500»)
    отбрасываются молча — врать в обе стороны хуже, чем промолчать.
    """
    for pattern in _EPISODE_SPAN_RES:
        match = pattern.search(text)
        if match:
            start, end = int(match.group("start")), int(match.group("end"))
            if 1 <= start <= end:
                return tuple(range(start, end + 1))
    match = _EPISODE_COUNT_RE.search(text)
    if match:
        count, total = int(match.group("count")), int(match.group("total"))
        if 1 <= count <= total:
            return tuple(range(1, count + 1))
    return ()


def _season_span(text: str) -> tuple[int, ...]:
    """Диапазон сезонов из имени раздачи: ``[S01-06]``, «1-6 сезоны» → (1…6)."""
    for pattern in _SEASON_SPAN_RES:
        match = pattern.search(text)
        if match:
            first, last = int(match.group(1)), int(match.group(2))
            if 0 < first < last <= 40:
                return tuple(range(first, last + 1))
    return ()


def _is_non_video(text: str) -> bool:
    """Музыка/книги/игры: не-видео маркеры при полном отсутствии видео-маркеров."""
    return bool(_NON_VIDEO_RE.search(text)) and not _VIDEO_MARKER_RE.search(text)


def _normalize_quality(value: str) -> str:
    lowered = value.lower()
    return "2160p" if lowered in {"4k", "uhd"} else lowered
