"""Часть разбора имён; публичный фасад — :mod:`torrcast.parse`."""

from __future__ import annotations

__all__ = ['TYPE_CHECKING', 'Callable', 'EpisodeFile', 'FileLike', 'Protocol', 'Sequence',
    '_bare_episode_span', '_base', '_collect', '_drop_small', '_read_bare', '_read_episode_only',
    '_read_order', '_read_sne', '_season_of', 'dataclass', 'map_episodes', 'parse_episode',
    'parse_release_name', 're', 'split_episode', 'statistics']

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.catalog import _find_year as _find_year
    from torrcast.catalog import _is_non_video as _is_non_video
    from torrcast.catalog import _normalize as _normalize
    from torrcast.catalog import _normalize_quality as _normalize_quality
    from torrcast.catalog import _parse_codec as _parse_codec
    from torrcast.catalog import _parse_series as _parse_series
    from torrcast.catalog import _parse_source as _parse_source
    from torrcast.catalog import _parse_voices as _parse_voices
    from torrcast.catalog import _split_titles as _split_titles
    from torrcast.catalog import _title_zone as _title_zone
    from torrcast.parse_name import _BRACKETS_RE as _BRACKETS_RE
    from torrcast.parse_name import _CYRILLIC as _CYRILLIC
    from torrcast.parse_name import _EPISODE_ONLY_RES as _EPISODE_ONLY_RES
    from torrcast.parse_name import _HDR_RE as _HDR_RE
    from torrcast.parse_name import _JUNK_RE as _JUNK_RE
    from torrcast.parse_name import _LATIN as _LATIN
    from torrcast.parse_name import _QUALITY_RE as _QUALITY_RE
    from torrcast.parse_name import _SEASON_EPISODE_RES as _SEASON_EPISODE_RES
    from torrcast.parse_name import _SEASON_ONLY_RES as _SEASON_ONLY_RES
    from torrcast.parse_name import _SMALL_RATIO as _SMALL_RATIO
    from torrcast.parse_name import _TECH_TOKEN_RE as _TECH_TOKEN_RE
    from torrcast.parse_name import VIDEO_EXT as VIDEO_EXT
    from torrcast.parse_name import Episode as Episode
    from torrcast.parse_name import Kind as Kind
    from torrcast.parse_name import Release as Release


import re
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol


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
        if was is None or item.size > was.size:  # тот же номер дважды - берём файл крупнее
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


def _bare_episode_span(zone: str) -> tuple[int, ...]:
    """Диапазон серий в хвосте латинского имени: ``Serial Experiments Lain 1-13``.

    Голая пара чисел слишком похожа на диапазон частей сборника, поэтому признак узкий:
    счёт начинается с первой серии, содержит хотя бы три серии, а перед ним стоят не
    меньше трёх слов латиницей. Остальные формы читает общий разбор диапазонов.
    """
    match = re.search(r"^(.+?)\s+1\s*-\s*(\d{1,3})\s*$", zone)
    if not match or len(re.findall(r"[A-Za-z]+", match.group(1))) < 3:
        return ()
    end = int(match.group(2))
    return tuple(range(1, end + 1)) if 3 <= end <= 500 else ()


def parse_release_name(name: str) -> Release:
    """Разобрать имя раздачи в структуру (форматы — в докстринге модуля)."""
    text = _normalize(name)
    year, span = _find_year(text)
    zone, collection = _title_zone(text, span)
    bare_episodes = _bare_episode_span(zone)
    if bare_episodes:
        zone = re.sub(r"\s+1\s*-\s*\d{1,3}\s*$", "", zone)
    title, original, aliases = _split_titles(zone)
    names = (title, *((original,) if original else ()), *aliases)
    latin_names = sum(bool(_LATIN.search(part) and not _CYRILLIC.search(part)) for part in names)
    russian_names = sum(bool(_CYRILLIC.search(part)) for part in names)
    # У одной картины бывают два оригинальных и два переводных имени. Три пары уже
    # перечисляют три картины: «Хоббит / Нежданное путешествие / Пустошь Смауга / ...».
    collection = collection or (latin_names >= 3 and russian_names >= 3)

    quality_match = _QUALITY_RE.search(text)
    quality = _normalize_quality(quality_match.group(1)) if quality_match else None

    season, episode, seasons, episodes, series = _parse_series(text)
    if bare_episodes and not episodes:
        episodes, series = bare_episodes, True
    kind: Kind = "other" if _is_non_video(text) else ("tv" if series else "movie")

    return Release(
        raw_name=name,
        title=title,
        original=original,
        aliases=aliases,
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
        collection=collection,
    )
