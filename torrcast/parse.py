"""Парсер имён раздач и кластеризация франшиз.

Метаданных извне нет: всё, что мы знаем о картине, добывается из имени раздачи
(§3 ТЗ). Три задачи: имя раздачи → :class:`Release` (название, оригинал, год,
качество, кодек, озвучки); релизы → :class:`Picture`-кластеры (франшиза = общее
каноническое название, сортировка по году даёт нумерацию, §2.2); разбор эпизодов
``s01e05`` / ``2x5`` / «2 сезон 5 серия» (§2.4).

Разбор свой, не guessit (обоснование — ``docs/parser.md``). Форматы, которые
модуль обязан понимать (проверено на корпусе из 21 540 реальных имён):

* rutor/megapeer  ``Рус / Original (2024) BDRip 1080p от Кто-то | D, P, A``
* kinozal         ``Рус / Original / 2009 / ДБ, СТ / 4K, HEVC / Blu-Ray (2160p)``
* rutracker       ``Рус / Original (Режиссёр) [2009, США, боевик, BDRip] Dub + AVO``
* scene           ``The.Martian.2015.1080p.BluRay.x264-GRP``
* аниме           ``[Group] Title (2025) (WEB-DL 1080p H264) [ABCD1234] | alt``
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Final, Literal

__all__ = [
    "Episode",
    "Picture",
    "Release",
    "cluster",
    "franchise_key",
    "franchises",
    "parse_episode",
    "parse_release_name",
    "part_number",
    "pick_franchise",
    "slugify",
    "split_franchise_index",
]

Kind = Literal["movie", "tv", "other"]

_CYRILLIC: Final = re.compile(r"[а-яё]", re.IGNORECASE)
_UKRAINIAN: Final = re.compile(r"[іїєґ]", re.IGNORECASE)
_LATIN: Final = re.compile(r"[a-z]", re.IGNORECASE)

_QUALITY_RE: Final = re.compile(r"\b(2160p|1080p|720p|576p|480p|360p|4k|uhd)\b", re.IGNORECASE)
_HEVC_RE: Final = re.compile(r"\b(hevc|h\.?\s?265|x265)\b", re.IGNORECASE)
_H264_RE: Final = re.compile(r"\b(avc|h\.?\s?264|x264)\b", re.IGNORECASE)
_AV1_RE: Final = re.compile(r"\bav1\b", re.IGNORECASE)
_HDR_RE: Final = re.compile(r"\b(hdr10\+?|hdr|dolby\s*vision|dv)\b", re.IGNORECASE)

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
    (r"dvd-?rip|\bdvd\d?\b", "DVDRip"),
    (r"\bts\b|\bcam\b|hdcam|telesync", "CAM"),
)

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
    re.compile(r"(?P<season>\d{1,2})\s*сезон\D{0,14}?(?P<episode>\d{1,3})\s*сери", re.IGNORECASE),
    re.compile(r"(?P<episode>\d{1,3})\s*сери\D{0,14}?(?P<season>\d{1,2})\s*сезон", re.IGNORECASE),
)
_SEASON_ONLY_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bs\s?(?P<season>\d{1,2})\b(?!\s?e)", re.IGNORECASE),
    re.compile(r"(?P<season>\d{1,2})[-\s]*(?:й\s*)?сезон", re.IGNORECASE),
    re.compile(r"season\s*(?P<season>\d{1,2})", re.IGNORECASE),
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
    size: int = 0
    seeders: int = 0
    magnet: str = ""
    indexer: str = ""
    kind: Kind = "movie"

    @property
    def is_hevc(self) -> bool:
        """HEVC показываем с пометкой ⚠ и никогда не берём по умолчанию (§3)."""
        return self.codec == "HEVC"

    @property
    def height(self) -> int:
        """Высота кадра из качества; 0 — качество в имени не указано."""
        digits = (self.quality or "").rstrip("p")
        return int(digits) if digits.isdigit() else 0

    @property
    def prime(self) -> bool:
        """Релиз первого сорта: H.264 и известное качество ≥720p — только из таких
        выбирается дефолт, иначе обсиженный DVDRip обгоняет живой 1080p (§2.1, §3).
        """
        return self.codec == "H.264" and self.height >= 720

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
        """Ключ состояния: ``<тип>:<slug>:<год>`` (§4 ТЗ)."""
        return f"{self.kind}:{slugify(self.title)}:{self.year if self.year else '0'}"

    @property
    def franchise(self) -> str:
        return franchise_key(self.title)

    @property
    def seeders(self) -> int:
        return max((r.seeders for r in self.releases), default=0)

    @property
    def best_release(self) -> Release | None:
        """Дефолт меню: самый обсиженный среди релизов первого сорта (H.264, ≥720p);
        нет таких — просто самый обсиженный (§2.1, §3).
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
    сохраняется, ключи из §4 ТЗ русские (``movie:матрица:1999``).
    """
    normalized = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    return re.sub(r"[^0-9a-zа-я]+", "-", normalized).strip("-")


def franchise_key(title: str) -> str:
    """Каноническое имя франшизы: «Матрица: Перезагрузка» и «Тачки 3» → одна серия.
    Режем подзаголовок после двоеточия и хвостовой номер части — именно они
    отличают фильмы внутри франшизы (§2.2).
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


def split_franchise_index(query: str) -> tuple[str, int | None]:
    """Отделить хвостовой номер франшизы: ``«матрица 2»`` → ``("матрица", 2)``. Номер —
    позиция в отсортированной по году франшизе, а не часть названия (§2.2);
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


def parse_release_name(name: str) -> Release:
    """Разобрать имя раздачи в структуру (форматы — в докстринге модуля)."""
    text = _normalize(name)
    year, span = _find_year(text)
    title, original = _split_titles(_title_zone(text, span))

    quality_match = _QUALITY_RE.search(text)
    quality = _normalize_quality(quality_match.group(1)) if quality_match else None

    season, episode, series = _parse_series(text)
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
        kind=kind,
    )


def cluster(releases: list[Release]) -> list[Picture]:
    """Сгруппировать релизы в картины; порядок = хронология франшизы (§2.2).
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
    номер — индекс в хронологии, а не часть названия (§2.2).
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
        hits = [k for k in groups if wanted in k]
        return min(hits, key=len) if hits else None

    name, index = split_franchise_index(query)
    key = lookup(name)
    if key is None:  # номер оказался частью названия: «пила 8», «форсаж 6»
        key, index = lookup(query), None
    if key is None:
        return []

    items = groups[key]
    if index is None:
        return items
    # Явный номер части сильнее позиции: «тачки 2» → «Тачки 2», а не спин-офф.
    explicit = [p for p in items if p.part == index]
    if explicit:
        return [max(explicit, key=lambda p: len(p.releases))]
    return [items[index - 1]] if 1 <= index <= len(items) else []


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
    if _HEVC_RE.search(text):
        return "HEVC"
    if _H264_RE.search(text):
        return "H.264"
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


def _parse_series(text: str) -> tuple[int | None, int | None, bool]:
    """Сезон, серия и признак сериальности."""
    found = parse_episode(text)
    if found is not None:
        # «S2E1-8 of 8» — это пак сезона, а не первая серия.
        pack = re.search(r"[eхx]\s*\d{1,3}\s*-\s*\d{1,3}", text, re.IGNORECASE)
        return found.season, None if pack else found.episode, True
    for pattern in _SEASON_ONLY_RES:
        match = pattern.search(text)
        if match:
            return int(match.group("season")), None, True
    return None, None, bool(_SERIES_HINT_RE.search(text))


def _is_non_video(text: str) -> bool:
    """Музыка/книги/игры: не-видео маркеры при полном отсутствии видео-маркеров."""
    return bool(_NON_VIDEO_RE.search(text)) and not _VIDEO_MARKER_RE.search(text)


def _normalize_quality(value: str) -> str:
    lowered = value.lower()
    return "2160p" if lowered in {"4k", "uhd"} else lowered
