"""Модель возможностей и порогов телевизора-приёмника."""

from dataclasses import dataclass
from typing import Final, Literal

from torrcast.domain.segment_container import MPEGTS, SegmentContainer

__all__ = [
    "CAUTIOUS",
    "COPY",
    "RECODE",
    "REFUSE",
    "ReceiverProfile",
    "Verdict",
]

COPY: Final = "copy"
RECODE: Final = "recode"
REFUSE: Final = "refuse"
Verdict = Literal["copy", "recode", "refuse"]


@dataclass(frozen=True, slots=True)
class ReceiverProfile:
    """Что телевизор умеет декодировать и как долго терпит ожидание.

    Значения по умолчанию — живые замеры Samsung Q70D. Это ограничения приёмника,
    не производительность машины, которая запускает torrcast.
    """

    key: str
    title: str
    #: Кодеки, которых приёмник не декодирует вовсе: такой файл перекодируется ЦЕЛИКОМ.
    #:
    #: 🔴 Решение принимается **на уровне файла**, по паспорту ffprobe, а не посегментно по
    #: весу и битрейту: замер на живом Q70D (07-08) - чистый лёгкий HEVC первым куском не
    #: берётся в LOAD вовсе (3 попытки из 3), а HEVC-сегмент в середине потока копий даёт
    #: вечный BUFFERING ровно на своей границе при упакованном запасе вперёд.
    #:
    #: Здесь hevc и mpeg4, и это не лень: цена перекода замерена ровно для них - у HEVC
    #: двукратный запас к реальному времени, у mpeg4 (XviD/DivX) девятнадцатикратный на
    #: DVDRip и тринадцатикратный на 720p. av1/vc1 остаются отказом отбора, пока такого же
    #: замера для них нет.
    #:
    #: ⚠️ Имени кодека для решения МАЛО, и это тоже замер: H.264 бывает десятибитным
    #: (:attr:`copy_depth`), зовётся всё тем же ``h264`` - и приёмник его не декодирует.
    #: Поэтому спрашивают :meth:`verdict`, а не членство в наборе.
    recode_codecs: frozenset[str] = frozenset({"hevc", "mpeg4"})
    copy_depth: int = 8
    copy_codecs: frozenset[str] = frozenset({"h264"})
    copy_10bit_codecs: frozenset[str] = frozenset()
    segment_container: SegmentContainer = MPEGTS
    recode_frame: int = 1080
    max_segment_bytes: int = 16_000_000
    #: Потолок ДЛИНЫ одного куска, секунды; ``0`` - потолка нет и сетку держит только вес.
    #:
    #: 🔴 Это не про декодер, а про окно, которым приёмник забирает куски: он просит
    #: следующий, когда впереди остаётся ровно столько-то плёнки, и кусок длиной в это
    #: окно оставляет его с единственным куском в запасе. У осторожного профиля окно не
    #: мерено, поэтому тут ноль: старое поведение сохраняется знак в знак.
    max_segment_seconds: float = 0.0
    segment_seconds: float = 10.0
    warn_mbit: float = 16.0
    recode_at_mbit: float = 10.0
    recode_mbit: float = 9.0
    burst: float = 60.0
    hold_seconds: float = 120.0
    start_buffer: float = 10.0
    #: Сколько приёмник терпит стоящую картинку, прежде чем умрёт медиасессия.
    patience: float = 23.5
    #: Сколько приложение приёмника живёт на экране после смерти медиасессии.
    app_patience: float = 301.0
    #: Через сколько секунд приёмник сам сдаётся на мёртвом URL. У Q70D такого срока нет
    #: вовсе (ноль), а на приставке Android TV тот же Default Media Receiver ведёт себя
    #: иначе: мёртвый URL стоит ей одного запроса и ``IDLE/ERROR`` на 4-й секунде,
    #: перезаборов куска ноль. Это повадки КОНКРЕТНОГО приёмника, поэтому и живут в
    #: профиле, а не в классе заглушки.
    dead_url_seconds: float = 0.0
    #: Сколько раз повторяем LOAD, пока приёмник его не берёт.
    load_retries: int = 2
    #: Сколько раз приёмник САМ перезабирает пропавший кусок, прежде чем сдаться.
    #: ⚠️ Не «повторы LOAD»: ``media_session_id`` при этом не меняется, приёмник
    #: переспрашивает тот же кусок по HTTP. У Q70D их два, у приставки Android TV - ни
    #: одного.
    segment_retries: int = 2
    #: Сколько приёмник не берёт LOAD вовсе, поймав 404.
    sulk: float = 0.0
    #: Сколько ждём картинку, когда показ ВОЗОБНОВЛЯЮТ: перепаковка после перемотки
    #: назад за окно, возврат с паузы. Это окно, в котором показ ещё может вернуться
    #: в своё же приложение, поэтому оно и равно :attr:`app_patience`, а не сроку LOAD.
    revive_timeout: float = 300.0
    revive_pause: float = 60.0
    revive_drop: float = 4.0
    #: Неподвижный ``BUFFERING`` дольше этого - приёмник завис, и сторож подталкивает.
    stall_seconds: float = 8.0
    #: Столько секунд упаковки впереди позиции считаем доказательством «еда на столе».
    #: Меньше - приёмник ждёт нас, и лечится это упаковкой, а не перемоткой.
    ready_ahead: float = 8.0
    #: Шаг прыжка вперёд на каждом нудже: мимо куска, на котором приёмник споткнулся.
    stall_skip: float = 8.0
    #: Столько нуджей подряд без единого показанного кадра - и сторож умолкает.
    blind_nudges: int = 3
    #: Достаточность роя до показа: запас над реальным временем и начало честного окна.
    supply_ratio: float = 1.25
    supply_settle_seconds: float = 0.0

    def verdict(self, codec: str, depth: int = 0, frame: int = 0) -> Verdict:
        """Решить судьбу картинки одним правилом: копия, перекод или отказ."""
        name = codec or "h264"
        if name in self.recode_codecs:
            return RECODE
        if name not in self.copy_codecs:
            return REFUSE
        deep = depth > self.copy_depth
        deep_refused = deep and (depth > 10 or name not in self.copy_10bit_codecs)
        if deep_refused or frame > self.recode_frame:
            return RECODE
        return COPY

    def plays_copy(self, codec: str, depth: int = 0, frame: int = 0) -> bool:
        """Уедет ли файл на приёмник без перекодирования."""
        return self.verdict(codec, depth, frame) == COPY


CAUTIOUS: Final = ReceiverProfile(key="q70d", title="осторожный (Samsung Q70D)")
