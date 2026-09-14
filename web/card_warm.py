"""Раздача карточки греется одна на процесс, уходит вместе с карточкой и достаётся показу.

Карточка отбирает раздачу ради дорожек (:class:`web.voice_lookup.VoiceLookup`), и этот
же отбор - самое дорогое, что показ с карточки сделал бы после «Играть»: метаданные,
карта опорных кадров и голова файла (:func:`torrcast.adapters.stream_pack.warm_file.
warm_file`, :data:`~torrcast.domain.warm_open.HEAD_WARM`). Поэтому выбранная раздача
остаётся в TorrServer, пока карточка на экране, а показ забирает стенд отбора целиком,
а не заводит второй рядом. Прогрев один: новая карточка и уход с карточки его снимают.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from torrcast.ports.progress.progress import Progress
    from torrcast.usecases.select._prep import _Prep
    from torrcast.usecases.select_bench.bench import Bench

#: Сколько показ ждёт, пока отбор карточки отпустит стенд: отбор спрашивает индикатор
#: каждые 0.2 с, и дольше он не держит. Не отпустил - показ отбирает своим стендом.
LET_GO: Final = 5.0


class _StoppedError(Exception):
    """Отбор карточки снят: карточка ушла или стенд забирает показ."""


@dataclass(eq=False)
class _Warm:
    """Прогрев одной картины: чей стенд, снят ли он и чем кончился отбор."""

    key: str
    bench: Bench
    #: Стенд забрал показ: карточка его больше не убирает, а ответ ждёт от показа.
    taken: bool = False
    stop: threading.Event = field(default_factory=threading.Event)
    #: Отбор карточки вышел: стенд свободен для показа.
    out: threading.Event = field(default_factory=threading.Event)
    #: Раздача выбрана (или отбор кончился ничем): ответ дорожкам карточки.
    chosen: threading.Event = field(default_factory=threading.Event)
    prep: _Prep | None = None


@dataclass(eq=False)
class _Stoppable:
    """Индикатор отбора карточки, который выходит из отбора, когда прогрев сняли."""

    inner: Progress
    halt: threading.Event

    def phase(self, text: str) -> None:
        if self.halt.is_set():
            raise _StoppedError
        self.inner.phase(text)

    def note(self, text: str) -> None:
        self.inner.note(text)

    def stop(self) -> None:
        self.inner.stop()

    def __enter__(self) -> _Stoppable:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        return None


class CardWarm:
    """Единственный прогрев раздачи карточки в процессе."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: _Warm | None = None

    def holds(self, key: str) -> bool:
        """Греется ли (или уже отбирается показом) раздача этой картины."""
        with self._lock:
            return self._current is not None and self._current.key == key

    def open(self, key: str, make: Callable[[], Bench]) -> tuple[_Warm, bool]:
        """Прогрев картины для карточки; правда - завели новый, прежний при этом снят.

        Картину уже отбирает показ - новый стенд не заводится: ответ приедет от показа.
        """
        with self._lock:
            old = self._current
            if old is not None and old.key == key:
                return old, False
            self._current = warm = _Warm(key, make())
        if old is not None:
            self._release(old)
        return warm, True

    @staticmethod
    def progress(warm: _Warm, inner: Progress) -> Progress:
        """Индикатор отбора карточки, снимаемый уходом карточки и показом."""
        return _Stoppable(inner, warm.stop)

    @staticmethod
    def stopped() -> type[Exception]:
        """Чем выходит снятый отбор карточки."""
        return _StoppedError

    def finish(self, warm: _Warm, prep: _Prep | None) -> None:
        """Отбор карточки вышел: выбранная раздача остаётся, прочее убирается."""
        with self._lock:
            warm.out.set()
            if warm.taken:  # стенд уже у показа, и убирать с него нечего
                return
            keep = prep is not None and self._current is warm and not warm.stop.is_set()
            if keep and prep is not None:
                prep.card_warmed = True
                warm.prep = prep
            elif self._current is warm:
                self._current = None
        if keep and prep is not None:
            warm.bench.keep_only(prep)
        else:
            warm.bench.drop_all()
        warm.chosen.set()

    def leave(self, key: str) -> None:
        """Карточка ушла с экрана: её прогрев снимается, а чужой остаётся."""
        with self._lock:
            warm = self._current
            if warm is None or warm.key != key or warm.taken:
                return
            self._current = None
        self._release(warm)

    def take(self, key: str, fresh: Bench) -> Bench:
        """Стенд показу с карточки: прогретый карточкой, иначе ``fresh``, названный её ключом.

        Судит показ своим профилем и своим выбором файла. Раздачи, которые отбор карточки
        уже убрал, со стенда уходят: у показа свой профиль, и такую раздачу он может
        взять - а в TorrServer её уже нет.
        """
        old: _Warm | None = None
        with self._lock:
            warm = self._current
            if warm is not None and warm.key == key and not warm.taken:
                warm.taken = True
                warm.stop.set()
            else:
                old = warm
                warm = None
                self._show(key, fresh)
        if warm is None:
            if old is not None and old.key != key:
                self._release(old)
            return fresh
        warm.out.wait(LET_GO)
        with self._lock:
            if not warm.out.is_set():  # отбор карточки не отпустил: уберёт за собой сам
                warm.taken = False
                self._show(key, fresh)
                return fresh
        bench = warm.bench
        bench.profile, bench.choose = fresh.profile, fresh.choose
        bench.preps = {at: prep for at, prep in bench.preps.items() if not prep.dropped}
        return bench

    def _show(self, key: str, fresh: Bench) -> None:
        """Картину отбирает показ своим стендом: дорожки карточки ждут его ответа."""
        warm = _Warm(key, fresh, taken=True)
        warm.out.set()
        self._current = warm

    def settled(self, bench: Bench, prep: _Prep | None) -> None:
        """Показ выбрал раздачу (или не выбрал): ответ дорожкам, стенд дальше только его."""
        with self._lock:
            warm = self._current
            if warm is None or warm.bench is not bench:
                return
            self._current = None
        warm.prep = prep
        warm.chosen.set()

    def _release(self, warm: _Warm) -> None:
        """Снять прогрев: идущий отбор уберёт за собой сам, вышедший убирается здесь."""
        warm.stop.set()
        with self._lock:
            done = warm.out.is_set() and not warm.taken
        if done:
            warm.bench.drop_all()
            warm.chosen.set()


CARD_WARM: Final = CardWarm()
