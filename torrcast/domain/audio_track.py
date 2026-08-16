"""Описывает звуковую дорожку и определяет её язык."""

import re
from dataclasses import dataclass
from typing import Final

from torrcast.domain.studio import Studio
from torrcast.domain.studio_of import studio_of

_RU_LANG: Final = frozenset({"rus", "ru", "russian", "рус"})
_VAGUE_LANG: Final = frozenset({"", "und", "unk", "unknown", "mul", "mis", "zxx", "qaa"})
_FOREIGN_TITLE_RE: Final = re.compile(
    "укр|ukr|каз|kaz|қаз|беларус|bel\\b|eng\\b|англ|original|ориг", re.IGNORECASE
)
_RU_TITLE_RE: Final = re.compile(
    "\\brus?\\b|русск|дубляж|дублир|многоголос|закадр|двухголос|одноголос|перевод|авторск",
    re.IGNORECASE,
)
_SERVICE_RE: Final = re.compile(
    "слабовидящ|тифлокоммент|коммент|commentary|audio\\s*descr|described", re.IGNORECASE
)
_ORIGINAL_RE: Final = re.compile("original|\\borig\\b|ориг", re.IGNORECASE)
_VOICE_STEPS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "дубляж",
        re.compile(
            "дубляж|дублир|\\bdub(?:bed|bing)?\\b|\\bдб\\b|лицензи|itunes|professional\\s*dub",
            re.IGNORECASE,
        ),
    ),
    ("многоголосый", re.compile("многоголос|закадр|\\bmvo\\b|\\bпм\\b|\\bлм\\b", re.IGNORECASE)),
    ("двухголосый", re.compile("двухголос|\\bdvo\\b|\\bдвг\\b", re.IGNORECASE)),
    (
        "одноголосый",
        re.compile("одноголос|авторск|\\bavo\\b|\\bvo\\b|\\bло\\b|\\bап\\b", re.IGNORECASE),
    ),
)
VOICE_KINDS: Final[tuple[str, ...]] = tuple((name for name, _ in _VOICE_STEPS))
STEP_RU_PLAIN: Final = len(_VOICE_STEPS)
STEP_ORIGINAL: Final = STEP_RU_PLAIN + 1
STEP_FOREIGN: Final = STEP_RU_PLAIN + 2
STEP_SERVICE: Final = STEP_RU_PLAIN + 3
_TECH_RE: Final = re.compile(
    "^(?:ac3|eac3|dts(?:-hd)?(?:\\s*ma)?|aac|mp3|flac|opus|truehd|pcm|lpcm|dd\\+?|ddp|\\d+\\s*ch|\\d+\\s*kbps|\\d+(?:[.,]\\d+)?\\s*k?hz|\\d+\\s*bit|\\d\\.\\d)\\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AudioTrack:
    index: int
    language: str | None = None
    title: str | None = None
    codec: str | None = None
    channels: int = 0

    @property
    def label(self) -> str:
        """Человеческая подпись озвучки: «rus · Дубляж (MovieDalen)».

        Она же ключ памяти (:attr:`torrcast.state.Entry.voice`), поэтому технический
        хвост из неё убран: «DUB (Rus) / AC3 / 6 ch / 384 kbps / 48 kHz» — это одна и та
        же озвучка что с битрейтом в имени, что без.
        """
        lang = self.language
        if (lang or "").strip().casefold() in _VAGUE_LANG:
            lang = None
        parts = [p for p in (lang, self.clean_title) if p]
        return " · ".join(parts) if parts else f"дорожка {self.index + 1}"

    @property
    def clean_title(self) -> str:
        """Заголовок без технического хвоста (кодек, каналы, битрейт, частота)."""
        kept: list[str] = []
        for chunk in (self.title or "").split("/"):
            if _TECH_RE.match(chunk.strip()):
                break
            kept.append(chunk.strip())
        return " / ".join(p for p in kept if p).strip(" .")

    @property
    def named(self) -> bool:
        """Назвала ли раздача язык дорожки. ``und``/``unk`` и пустой тег — это «не
        назвала» (:data:`_VAGUE_LANG`): язык неизвестен, и выдавать его за русский
        нельзя (:func:`torrcast.cli.sound_note`)."""
        return (self.language or "").strip().casefold() not in _VAGUE_LANG

    @property
    def is_russian(self) -> bool:
        """Русская ли дорожка. Тег языка сильнее заголовка: «Дубляж» с тегом ``kaz`` —
        казахский дубляж, и слышать его никто не хотел (живой случай «Тачки 3»).
        """
        lang = (self.language or "").strip().casefold()
        if lang in _RU_LANG:
            return True
        if lang not in _VAGUE_LANG:
            return False
        title = self.title or ""
        named = _RU_TITLE_RE.search(title) or studio_of(title) is not None
        return bool(named) and (not _FOREIGN_TITLE_RE.search(title))

    @property
    def studio(self) -> Studio | None:
        """Знакомая студия из заголовка (:func:`studio_of`); ``None`` — не узнали."""
        return studio_of(self.title)

    @property
    def kind(self) -> str:
        """Вид перевода словами: ``дубляж``, ``многоголосый``…; пусто — маркера нет.

        Сперва спрашиваем сам заголовок, и только потом таблицу студий: «MVO. (Jaskier)»
        - это многоголосый, хотя дубляжи Jaskier делает тоже. Что дорожка про себя
        написала, всегда точнее, чем что мы знаем про студию вообще.
        """
        title = self.title or ""
        if named := next((name for name, rx in _VOICE_STEPS if rx.search(title)), ""):
            return named
        studio = self.studio
        return studio.kind if studio else ""

    @property
    def step(self) -> int:
        """Ступень лестницы «самой нормальной» озвучки; меньше — ближе к дефолту."""
        title = self.title or ""
        if _SERVICE_RE.search(title):
            return STEP_SERVICE
        if not self.is_russian:
            return STEP_ORIGINAL if _ORIGINAL_RE.search(title) else STEP_FOREIGN
        steps = (i for i, (name, _) in enumerate(_VOICE_STEPS) if name == self.kind)
        return next(steps, STEP_RU_PLAIN)

    @property
    def rank_step(self) -> int:
        """Ступень, по которой дорожку судят на отборе; обычно это :attr:`step`.

        Расходится с ней только там, где студия крутее своего вида перевода
        (:attr:`Studio.ranks`). Поднимаем, а не опускаем: если дорожка уже назвалась
        дубляжом, отборная ступень студии её не ухудшает. Нерусские и служебные дорожки
        не трогаем вовсе - там ступень означает не качество перевода, а язык.
        """
        step = self.step
        studio = self.studio
        if step >= STEP_RU_PLAIN or studio is None or (not studio.ranks):
            return step
        ranks = (i for i, (n, _) in enumerate(_VOICE_STEPS) if n == studio.ranks)
        return min(step, next(ranks, step))
