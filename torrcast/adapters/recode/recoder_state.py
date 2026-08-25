"""Поля фонового кодировщика и мелкие справки по ним.

Наследует их :class:`torrcast.adapters.recode.recoder.Recoder`, и только он."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.recode.oversize import oversize
from torrcast.adapters.recode.pace import Pace
from torrcast.adapters.recode.recoder_settings import RUN_MAX
from torrcast.adapters.recode.targets import _targets
from torrcast.adapters.recode.weights import Weights
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.segment_container import MPEGTS, SegmentContainer
from torrcast.ports.pack_run.pack_factory import PackFactory

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.adapters.stream_pack.grid import Grid


@dataclass(slots=True)
class _State:
    """Всё, что кодировщик про себя знает: настройки показа и ход текущего прогона."""

    source: str
    audio: int
    grid: Grid
    spare: Path
    weights: Weights
    threshold: float = 15.0
    #: Потолок веса одного куска - свойство ПРИЁМНИКА
    #: (:attr:`torrcast.domain.profile.Profile.max_segment_bytes`), то же число, которым
    #: меряет показ (:attr:`torrcast.usecases.feed_pack.feed.Feed.cap`). Раньше каталог
    #: перекода судил по :data:`torrcast.domain.hls_settings.MAX_SEGMENT_BYTES` -
    #: осторожному умолчанию, - и приёмник с
    #: другим потолком получал от кодировщика не свою мерку. Умолчание тут то же
    #: осторожное, так что для Q70D не меняется ничего.
    cap: int = CAUTIOUS.max_segment_bytes
    #: Контейнер кусков - свойство ПРИЁМНИКА
    #: (:attr:`torrcast.domain.profile.Profile.segment_container`), тот же, каким режет
    #: показ. Кодировщик кладёт свои куски рядом с кусками показа и под теми же именами,
    #: и расширение у них обязано быть одно: под чужим расширением готовый перекод
    #: невидим выкладке, а место уходит в круг без прогресса.
    container: SegmentContainer = MPEGTS
    encode: Encode = field(default_factory=Encode)
    #: Горизонт: дальше этого места фильма впрок не работаем. Ограничение не по времени, а
    #: по tmpfs - готовые куски лежат в памяти. Модель показа «Моаны 2»: 300 с горизонта
    #: держат пик кэша на 459 МБ и не стоят ни одного опоздания.
    ahead: float = 300.0
    #: Потолок кэша перекодированного, МБ. Достигнут - кодировщик спит, а не растёт.
    cache_mb: float = 384.0
    run_max: int = RUN_MAX
    #: Запас, с которым перекод обязан успеть, чтобы его стоило ждать (секунды).
    hold_guard: float = 2.0
    #: Сколько кодировщику отпущено на подъём первого захода. Пока он поднимается,
    #: упаковщик уже выкладывает ``burst`` - и без этой форы первые тяжёлые куски успевали
    #: уйти копией просто потому, что ffmpeg ещё не стартовал.
    grace: float = 6.0
    #: Во сколько секунд обходится подъём одного захода: ffmpeg открывает вход, TorrServer
    #: доезжает до нужного места. Замер - 1-3 с, берём верх.
    startup: float = 3.0
    #: Потолок ожидания перекода ПЕРВОГО сегмента прогона (:meth:`opening`), секунды.
    #: Умолчание и его замер - :attr:`torrcast.domain.config.Config.recode_head_wait`.
    head_wait: float = 12.0
    #: Сколько ЖДЁМ перекод куска, копия которого тяжелее потолка (:meth:`_hold_bulky`),
    #: секунды. Это не срок «успеет ли», а предохранитель от вечного ожидания: копию
    #: тяжелее :data:`torrcast.domain.hls_settings.MAX_SEGMENT_BYTES` по сроку не отпускают вовсе, и
    #: без потолка сдохший кодировщик держал бы показ до 404.
    #:
    #: 45 с - с запасом впятеро: самый длинный кусок сетки (20 с фильма) ultrafast'ом
    #: считается 5 с, плюс подъём захода 3 с, плюс доработка чужого захода (до 6 кусков).
    over_wait: float = 45.0
    #: Фактическая скорость перекода на этом показе (:class:`Pace`). Всё, что считает срок,
    #: спрашивает её, а не :data:`PRESETS` напрямую.
    pace: Pace = field(default_factory=Pace)
    #: Чем поднимать заход. Полем, а не именем внутри :func:`_run`: сам заход - это
    #: процесс ffmpeg, а меряется тут команда, которую ему собрали, и то, чем заход
    #: сочли. Договор ему называет порт (:class:`PackFactory`), а кем он будет на самом
    #: деле, решает тот, кто собирает кодировщик.
    packer_type: PackFactory = Packer
    log: Any = None

    #: Где сейчас показ; обновляет :func:`torrcast.usecases.revive_playback._hold._hold`.
    played: float = 0.0
    #: Докуда дошла упаковка - последний выложенный наружу сегмент (:meth:`note`).
    #:
    #: ⚠️ Срок готовности считается от НЕЁ, а не от места показа, и это не мелочь.
    #: Упаковщик идёт впереди показа на ``burst`` (60 с) и на старте выкладывает эти
    #: 60 секунд разом. Считай кодировщик срок по показу - и он спокойно взялся бы за
    #: заход на полторы минуты, пока упаковщик уже выложил тяжёлые куски как есть.
    #: Ровно это и было видно в первом прогоне: v361 и v362 (26 и 28 Мбит/с) ушли копией,
    #: потому что кодировщик считал, что до них ещё полторы минуты.
    edge: int = -1
    #: Первый сегмент текущего прогона упаковки - тот, с которого пойдёт картинка
    #: (:meth:`opening`). ``-1`` - упаковка ещё не начиналась.
    head: int = -1
    #: Когда этот прогон начался (``time.monotonic``): от неё считается :attr:`head_wait`.
    head_at: float = 0.0
    done: set[int] = field(default_factory=set)
    late: int = 0
    made: int = 0
    seconds: float = 0.0
    stopped: bool = False
    #: Что кодировщик делает прямо сейчас: ``(первый слот, последний, крайний срок,
    #: когда начали, скорость пресета)``. По нему же решается, придерживать ли копию.
    job: tuple[int, int, float, float, float] | None = None
    #: Когда кодировщик подняли (:meth:`start`).
    began: float = 0.0
    #: Слот, на котором ВСТАЛА выкладка из-за слишком тяжёлой копии (:meth:`_hold_bulky`);
    #: ``-1`` - не встала. По нему кодировщик бросает чужой заход: пока упаковка стоит,
    #: работа впрок не стоит ничего (:meth:`_run`).
    blocked: int = -1
    #: С какой секунды держим слишком тяжёлую копию: слот → ``time.monotonic``.
    stuck: dict[int, float] = field(default_factory=dict)
    #: Кусок, который выкладка ужимает на месте сама, и когда она за него взялась
    #: (:meth:`_hold_bulky`); ``None`` - никто ничего не ужимает. Пока ужатие идёт, заход
    #: замирает и отдаёт ему процессор (:meth:`_yield_to_shrink`).
    shrinking: tuple[int, float] | None = None
    #: Сколько секунд этот заход простоял, уступая ужатию. Из замера темпа вычитается:
    #: пауза мерит вежливость, а не скорость кодека (:meth:`Pace.record`).
    stalled: float = 0.0
    thread: Any = None
    packer: Any = None
    lock: Any = field(default_factory=threading.Lock)

    def fit(self, span: float, preset: str) -> Encode:
        """Цель одного куска по обоим потолкам этого приёмника."""
        return replace(self.encode, preset=preset).fit(span, self.cap, self.threshold)

    @property
    def working(self) -> bool:
        """Идёт ли заход прямо сейчас.

        По этому и уступает прогрев (:class:`torrcast.usecases.warm.warmer.Warmer`).

        Замер, ради которого свойство появилось: живой перекод под работающим прогревом
        теряет 30 % скорости (:data:`NEIGHBOUR_TOLL`), а ``nice`` от этого не спасает -
        прогрев идёт под ``nice 19`` и всё равно забирает 128 % из 400 %.
        """
        return self.job is not None

    @property
    def targets(self) -> tuple[int, ...]:
        """Слоты, которые обязан взять кодировщик (:func:`_targets`)."""
        return _targets(self.weights, self.grid, self.threshold, self.cap)

    def oversize(self, slot: int, size: int = 0) -> bool:
        """Копия этого куска тяжелее потолка приёмника (:func:`oversize`)."""
        return oversize(self.weights, self.grid, self.cap, slot, size)

    def ready(self, slot: int) -> Path | None:
        """Путь к готовому перекодированному куску или ``None``."""
        path = self.spare / segment_name(slot, self.container)
        return path if path.exists() else None

    def _unstick(self, slot: int) -> None:
        """Кусок больше не держит выкладку: перекод готов, ушёл наружу или мы сдались."""
        self.stuck.pop(slot, None)
        if self.blocked == slot:
            self.blocked = -1

    def slack(self, slot: int) -> float:
        """Сколько секунд осталось до того, как этот кусок понадобится наружу.

        Считается от упаковщика, а не от показа: наружу сегмент выкладывает он, и опоздать
        к нему — значит выпустить тяжёлый кусок как есть (см. :attr:`edge`).
        """
        reached = self.grid.end(self.edge) if self.edge >= 0 else self.played
        return self.grid.start(slot) - max(self.played, reached)

    def _say(self, text: str) -> None:
        if self.log is not None:
            self.log(text)
