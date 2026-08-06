"""Конфиг и состояние просмотра: ``/etc/torrcast/config.json`` (обязателен только
адрес ТВ) и ``/var/lib/torrcast/state.json`` (структура записи — §4 ТЗ, запись
атомарная: tmp + rename). Обе точки переопределяются переменными окружения
``TORRCAST_STATE`` и ``TORRCAST_CONFIG`` — это нужно тестам и стенду.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from torrcast import TorrcastError

__all__ = ["Config", "Entry", "State", "config_path", "load_config", "save_config", "state_path"]

Kind = Literal["movie", "tv"]

DEFAULT_STATE_PATH = Path("/var/lib/torrcast/state.json")
DEFAULT_CONFIG_PATH = Path("/etc/torrcast/config.json")

#: Доля длительности, после которой позиция считается «досмотрено» (§2.4).
WATCHED_RATIO = 0.95


def state_path() -> Path:
    """Путь к файлу состояния с учётом ``TORRCAST_STATE``."""
    return Path(os.environ.get("TORRCAST_STATE") or DEFAULT_STATE_PATH)


def config_path() -> Path:
    """Путь к конфигу с учётом ``TORRCAST_CONFIG``."""
    return Path(os.environ.get("TORRCAST_CONFIG") or DEFAULT_CONFIG_PATH)


@dataclass(slots=True)
class Config:
    """Настройки. Обязателен только ``tv``; остальное имеет рабочие дефолты."""

    tv: str | None = None
    receiver: Literal["chromecast", "mock"] = "chromecast"
    torrserver_url: str = "http://127.0.0.1:8090"
    prowlarr_url: str = "http://127.0.0.1:9696"
    prowlarr_apikey: str = ""
    #: Чем раздаём HLS. Дефолт — ``http`` (§5 SPEC-v2): ни серта, ни имени, ни облака в
    #: пути потока. ``https`` — выключенная опция: код жив и работает, но требует серта,
    #: которому доверяет ТВ, а с ним — имени и того, кто это имя выпишет.
    transport: Literal["http", "https"] = "http"
    #: База URL, под которой ТВ забирает HLS. **Пусто — нормальный режим**: адрес
    #: вычисляется по маршруту до ТВ (:func:`torrcast.stream.hls_base`), то есть берётся
    #: та наша нога, с которой нас видит сам телевизор. DNS в пути показа не участвует
    #: вовсе — упадёт AdGuard, каст продолжит играть (§5 SPEC-v2). Задавать руками стоит
    #: ровно в одном случае: прямой путь почему-то не работает и нужен другой адрес.
    hls_base_url: str = ""
    hls_port: int = 8080
    #: Серт и ключ: нужны только при ``transport: https`` (§9).
    hls_cert: str = "/etc/torrcast/tls/torrcast.crt"
    hls_key: str = "/etc/torrcast/tls/torrcast.key"
    #: Сегменты живут в tmpfs — фильм на диск не пишем (§3). Целиком он туда и не
    #: влезет: в каталоге всегда только окно вокруг того места, где смотрят (§2.1 SPEC-v2).
    hls_dir: str = "/dev/shm/torrcast"
    #: Темп упаковки — ровно реальное время, а запас впереди приёмника даёт burst (§6
    #: SPEC-v2). Пара 1.0/60 держит упаковку на ~минуту впереди показа и не растёт: в
    #: tmpfs всегда ``burst`` + ``hls_keep`` секунд фильма, сколько бы он ни длился.
    #: ⚠️ 1.0 БЕЗ burst дважды вреден, замерено 05-08-2026: первый сегмент готов не раньше
    #: своей же длительности (на «Моане 2» ключевые кадры дают ~12 с сегменты → +9 с к
    #: старту), а дальше приёмник идёт вровень с упаковкой и буферится на каждом стыке.
    #: Темп заметно выше единицы (было 1.5) уводит упаковку вперёд без предела — на
    #: двухчасовом фильме это лишний час потока в RAM.
    hls_readrate: float = 1.0
    #: Сколько секунд входа ffmpeg читает на полной скорости, прежде чем встать в темп
    #: (``-readrate_initial_burst``, нужен ffmpeg ≥ 6.1 — на стенде его ставит install.sh).
    hls_burst: float = 60.0
    #: Сколько секунд позади приёмника держим сегменты — это и есть глубина перемотки
    #: назад «без последствий». Глубже — не 404, а перепаковка потока с нужной секунды.
    hls_keep: float = 120.0
    #: Шаг сетки сегментов, секунды. Не «длительность»: с сеткой по опорным кадрам
    #: сегмент длиннее шага на остаток GOP (:class:`torrcast.stream.Grid`).
    hls_segment: float = 10.0
    #: Ставить границы сегментов на опорные кадры (нужна карта из mkv). Так каждый кусок
    #: декодируется сам по себе и перемотка в любую точку сразу даёт картинку. ``false`` —
    #: ровная сетка ровно по ``hls_segment``: это режим для замеров, а не для показа.
    hls_keyframes: bool = True
    #: Практический потолок битрейта приёмника, Мбит/с (урок Q70D, §3).
    #:
    #: ⚠️ 16, а не 20: замер на живом Q70D 06-08-2026 — честный 1080p «Моаны 2» на
    #: 17.8 Мбит/с встаёт в ребуфер раз в 30–60 секунд при полной упаковке впереди, и
    #: каждый такой подвис стоит 8 с пропущенного фильма (§7.5 SPEC-v2). Решение владельца:
    #: смотрибельность важнее пиковой чёткости. Тяжёлый релиз по-прежнему берётся руками
    #: (``--release N``) — он остаётся в таблице с пометкой «тяжёлый».
    bitrate_warn_mbit: float = 16.0

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Config:
        """Собрать конфиг из словаря, молча игнорируя незнакомые ключи."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def load_config() -> Config:
    """Прочитать конфиг; отсутствующий файл — не ошибка, а дефолты."""
    path = config_path()
    if not path.exists():
        return Config()
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TorrcastError(f"битый конфиг {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TorrcastError(f"битый конфиг {path}: ожидался объект JSON")
    return Config.from_json(raw)


def save_config(config: Config) -> None:
    """Записать конфиг атомарно, создав каталог при необходимости."""
    _write_atomic(config_path(), asdict(config))


@dataclass(slots=True)
class Entry:
    """Запись состояния: что смотрим, чем и с какого места (§4 ТЗ)."""

    title: str
    magnet: str
    kind: Kind = "movie"
    file_idx: int = 0
    audio: int = 0
    #: Память озвучки на эту картину (правка владельца 06-08 к §2 SPEC-v2): подпись
    #: дорожки (:attr:`torrcast.stream.AudioTrack.label`), которую владелец выбрал
    #: **явно** — флагом ``--voice``. Пусто — явного выбора не было.
    #:
    #: Почему подпись, а не номер: номер живёт внутри одного релиза, а память — на
    #: картину. Следующий запуск может взять другую раздачу (сиды меняются, верх отбора
    #: тоже), и «дорожка 4» там будет другой студией. Подпись переживает смену релиза, а
    #: если такой озвучки в новом релизе нет — об этом говорится вслух и берётся дефолт,
    #: причём память НЕ стирается: релиз временный, выбор владельца — нет.
    #:
    #: Автовыбор сюда не пишет ничего: запоминается только то, что человек назвал сам.
    #: У сериала память общая на сериал — она и лежит в одной записи на всю раздачу.
    voice: str = ""
    pos: float = 0.0
    dur: float = 0.0
    #: Разрешение, ПОДТВЕРЖДЁННОЕ ffprobe у того файла, который играем
    #: (:attr:`torrcast.stream.Media.quality`). Заявка имени сюда не попадает никогда:
    #: «1080p» в заголовке и 1150×574 внутри — живой случай «Моаны 2», а `cast status`
    #: обязан показывать то, что уехало на ТВ (§1 v1: молчаливых подмен нет). Пусто —
    #: записи прежней версии, о них честно молчим.
    quality: str = ""
    season: int | None = None
    episode: int | None = None
    #: Серии раздачи по порядку: ``[сезон, серия, номер файла]`` (§2.4). Это и есть кэш
    #: выбора: стык серий и прыжок на s2e5 обходятся без Prowlarr и без вопросов.
    episodes: list[list[int]] = field(default_factory=list)
    #: Slug исходного запроса: по нему resume находит запись, не ходя в Prowlarr (§2.3).
    query: str = ""
    #: Досмотрено (§2.4). У фильма это конец истории, у сериала — повод взять следующую.
    done: bool = False
    updated: str = ""

    @property
    def watched(self) -> bool:
        """Досмотрено ли: позиция ≥ 95 % длительности (§2.4)."""
        return self.dur > 0 and self.pos >= self.dur * WATCHED_RATIO

    @property
    def resumable(self) -> bool:
        """Есть ли что продолжать: недосмотренный прогресс (§2.3)."""
        return self.pos > 0 and not self.done

    @property
    def serial(self) -> bool:
        """Правда ли это сериал: тип ``tv`` и в раздаче **несколько** серий.

        Одна серия в списке — это не сериал, а осечка разбора: так в состоянии осталась
        «Moana 2», которую ``x264`` в имени сделал s1e1 (дефект №3 владельца, §1
        SPEC-v2). Парсер починен, но записи-то остались, и строки «Серии: серий 1:
        s1e1…s1e1» в выводе фильма быть не должно ни у кого. Настоящей раздаче с одной
        серией это ничего не стоит: переходить всё равно некуда.
        """
        return self.kind == "tv" and len(self.episodes) > 1

    @property
    def label(self) -> str:
        """Подпись серии ``s1e2``; у фильма — пусто (§2.4)."""
        if not self.serial or self.season is None or self.episode is None:
            return ""
        return f"s{self.season}e{self.episode}"

    def where(self, season: int, episode: int) -> int:
        """Место серии в списке серий раздачи; ``-1`` — такой серии в раздаче нет."""
        for at, item in enumerate(self.episodes):
            if len(item) >= 2 and item[0] == season and item[1] == episode:
                return at
        return -1

    def jump(self, season: int, episode: int) -> Entry | None:
        """Прыжок на серию в пределах уже выбранной раздачи (§2.4): ни поиска, ни вопросов.
        Серии в раздаче нет — ``None``, и цепочка честно идёт искать релиз нужного сезона.
        """
        at = self.where(season, episode)
        if at < 0:
            return None
        return self._go(at)

    def advance(self) -> Entry:
        """Что записать по достижении порога 95 % (§2.4): фильму — пометка «досмотрено» и
        сброс позиции (следующий ``cast`` начнёт сначала), сериалу — следующая серия
        раздачи с нуля, выбор релиза и дорожки при этом сохраняется. Серия была
        последней — «досмотрено» и для сериала: конец сезона или конец раздачи.
        """
        at = self.where(self.season or 0, self.episode or 0)
        if self.kind == "tv" and 0 <= at < len(self.episodes) - 1:
            return self._go(at + 1)
        return replace(self, pos=0.0, done=True)

    def _go(self, at: int) -> Entry:
        """Встать на серию номер ``at`` списка: новый файл, позиция и длительность с нуля."""
        season, episode, file_idx = self.episodes[at][:3]
        return replace(
            self, season=season, episode=episode, file_idx=file_idx, pos=0.0, dur=0.0, done=False
        )

    def touch(self) -> Entry:
        """Копия записи со свежей меткой времени."""
        return replace(self, updated=datetime.now(UTC).astimezone().isoformat())

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Entry:
        fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        raw = fields.get("episodes")
        if isinstance(raw, list):  # битую строку списка серий лучше потерять, чем упасть
            fields["episodes"] = [
                [int(n) for n in item[:3]]
                for item in raw
                if isinstance(item, list) and len(item) >= 3
            ]
        return cls(**fields)


@dataclass(slots=True)
class State:
    """Состояние целиком: ключ ``<тип>:<slug>:<год>`` → :class:`Entry`."""

    entries: dict[str, Entry] = field(default_factory=dict)

    @classmethod
    def load(cls) -> State:
        """Прочитать состояние; отсутствующий или битый файл — пустое состояние."""
        try:
            raw: Any = json.loads(state_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        return cls({str(k): Entry.from_json(v) for k, v in raw.items() if isinstance(v, dict)})

    def save(self) -> None:
        _write_atomic(state_path(), {k: asdict(v) for k, v in self.entries.items()})

    def get(self, key: str) -> Entry | None:
        return self.entries.get(key)

    def find(self, query: str) -> tuple[str, Entry] | None:
        """Запись по запросу пользователя, без похода в Prowlarr (§2.3): сравниваем slug
        запроса с сохранённым запросом и со slug'ом в ключе; несколько — берём свежайшую.
        """
        from torrcast.parse import slugify

        want = slugify(query)
        if not want:
            return None
        hits = [(k, e) for k, e in self.entries.items() if want in {e.query, _slug(k)}]
        # Сериал зовут коротко: «киберпанк» вместо «киберпанк бегущие по краю» (§2.4).
        # Фильму так нельзя: «матрица» — это запрос франшизы, а не «Матрица: Перезагрузка».
        hits = hits or [
            (k, e) for k, e in self.entries.items() if e.kind == "tv" and _slug(k).startswith(want)
        ]
        return max(hits, key=lambda item: item[1].updated) if hits else None

    def latest(self) -> tuple[str, Entry] | None:
        """Самая свежая запись — то, что показывает ``cast status`` (§2.5)."""
        return max(self.entries.items(), key=lambda item: item[1].updated, default=None)

    def put(self, key: str, entry: Entry) -> None:
        """Положить запись, обновив метку времени."""
        self.entries[key] = entry.touch()

    def drop(self, key: str) -> None:
        """Забыть запись (``--new``)."""
        self.entries.pop(key, None)

    def __iter__(self) -> Iterator[tuple[str, Entry]]:
        return iter(self.entries.items())


def _slug(key: str) -> str:
    """Slug канонического названия из ключа ``<тип>:<slug>:<год>``."""
    return key.split(":")[1] if ":" in key else ""


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Записать JSON во временный файл рядом и переименовать поверх цели."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise TorrcastError(f"не смог записать {path}: {exc}") from exc
