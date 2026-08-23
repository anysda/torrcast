"""Модель измеренных возможностей и порогов телевизора-приёмника."""

from dataclasses import dataclass
from typing import Final, Literal

__all__ = [
    "ANDROID_TV",
    "CAUTIOUS",
    "COPY",
    "PROFILES",
    "RECODE",
    "REFUSE",
    "Profile",
    "Verdict",
]

COPY: Final = "copy"
RECODE: Final = "recode"
REFUSE: Final = "refuse"
Verdict = Literal["copy", "recode", "refuse"]


@dataclass(frozen=True, slots=True)
class Profile:
    """Что телевизор умеет декодировать и как долго терпит ожидание.

    Значения по умолчанию — живые замеры Samsung Q70D. Это ограничения приёмника,
    не производительность машины, которая запускает torrcast.
    """

    key: str
    title: str
    recode_codecs: frozenset[str] = frozenset({"hevc", "mpeg4"})
    copy_depth: int = 8
    copy_codecs: frozenset[str] = frozenset({"h264"})
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
    patience: float = 23.5
    app_patience: float = 301.0
    #: Через сколько секунд приёмник сам сдаётся на мёртвом URL. У Q70D такого срока нет
    #: вовсе (ноль), а на приставке Android TV тот же Default Media Receiver ведёт себя
    #: иначе: мёртвый URL стоит ей одного запроса и ``IDLE/ERROR`` на 4-й секунде,
    #: перезаборов куска ноль. Это повадки КОНКРЕТНОГО приёмника, поэтому и живут в
    #: профиле, а не в классе заглушки.
    dead_url_seconds: float = 0.0
    load_retries: int = 2
    #: Сколько раз приёмник САМ перезабирает пропавший кусок, прежде чем сдаться.
    #: ⚠️ Не «повторы LOAD»: ``media_session_id`` при этом не меняется, приёмник
    #: переспрашивает тот же кусок по HTTP. У Q70D их два, у приставки Android TV - ни
    #: одного.
    segment_retries: int = 2
    sulk: float = 0.0
    revive_timeout: float = 300.0
    revive_pause: float = 60.0
    revive_drop: float = 4.0
    stall_seconds: float = 8.0
    ready_ahead: float = 8.0
    stall_skip: float = 8.0
    blind_nudges: int = 3

    def verdict(self, codec: str, depth: int = 0, frame: int = 0) -> Verdict:
        """Решить судьбу картинки одним правилом: копия, перекод или отказ."""
        name = codec or "h264"
        if name in self.recode_codecs:
            return RECODE
        if name not in self.copy_codecs:
            return REFUSE
        if depth > self.copy_depth or frame > self.recode_frame:
            return RECODE
        return COPY

    def plays_copy(self, codec: str, depth: int = 0, frame: int = 0) -> bool:
        """Уедет ли файл на приёмник без перекодирования."""
        return self.verdict(codec, depth, frame) == COPY


CAUTIOUS: Final = Profile(key="q70d", title="осторожный (Samsung Q70D)")

ANDROID_TV: Final = Profile(
    key="androidtv",
    title="приставка Android TV (Xiaomi TV Stick)",
    # Живой замер на приставке (TC-620). У релиза, на котором мерили, индекс Cues врун,
    # карта опорных кадров отвергается, и сетка выходит ровная по 10 с: куски копии
    # 19.1-19.9 МБ. С осторожными 16 МБ наружу не выходит НИ ОДИН кусок: на ровной сетке
    # профиля тяжести нет, ужимать нечем, и выкладка честно пропускает каждый (39 из 39),
    # а показа нет вовсе - три прогона из трёх. С 28 МБ те же куски уезжают копией: КПД
    # 0.992-0.997 за 240 с показа, ни одной остановки, четыре прогона из четырёх, включая
    # прогон с пустой полки прогретого. Прощупан и сам потолок: куски 26.9-27.7 МБ (ровная
    # сетка по 14 с) приставка доигрывает 87 с подряд без единого подвиса.
    # У Q70D его 16 МБ остаются нетронутыми: это число снято на другом приёмнике.
    max_segment_bytes=28_000_000,
    # Живой замер окна запроса на приставке (TC-756): она просит следующий кусок, когда
    # впереди остаётся 20.0 с плёнки - медиана по 451 запросу двух прогонов, десятая доля
    # 19.8 с, самое тесное наблюдение 19.4 с. Кусок такой же длины оставляет её ровно с
    # одним куском в запасе, и на границе после него приставка САМА встаёт на паузу: 15 из
    # 15 её самопауз за два прогона по 13 минут пришлись на куски 19.7-27.9 с, и ни одной
    # на куски короче. По ленте показа то же: 9 подгрузов из 27 таких границ против 1 из
    # 179 остальных, а в архиве приёмки - 6 из 31 против 0 из 216.
    # 15 с - это середина промежутка между самым коротким сломавшимся куском (19.2 с) и
    # самой длинной проверенной живьём чистой нарезкой (14.5 с, 13 минут без единой
    # самопаузы): запас 4.2 с вниз от поломки и 4.4 с вниз от самого тесного окна.
    max_segment_seconds=15.0,
    warn_mbit=28.0,
    recode_at_mbit=28.0,
    # Верх цели - тот же измеренный поток, который приставка принимает нативно.
    # Длина куска и потолок 28 МБ опускают фактическую цель через Encode.fit.
    recode_mbit=28.0,
    patience=577.0,
    app_patience=577.0,
    dead_url_seconds=4.0,
    segment_retries=0,
    revive_timeout=577.0,
    revive_pause=10.0,
    revive_drop=10.0,
)

PROFILES: Final = {profile.key: profile for profile in (CAUTIOUS, ANDROID_TV)}
