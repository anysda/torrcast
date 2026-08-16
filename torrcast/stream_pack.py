"""Часть медиатракта; публичный фасад — :mod:`torrcast.stream`."""

from __future__ import annotations

__all__ = [
    "HEAD_WARM",
    "HLS_SEGMENT_SECONDS",
    "MAX_SEGMENT_BYTES",
    "PILOT_TIMEOUT",
    "TYPE_CHECKING",
    "Any",
    "FilmKeys",
    "Grid",
    "InfraError",
    "NamedTuple",
    "Path",
    "_extra_mbit",
    "_fetching",
    "_hold_keys_lock",
    "_keys_cache",
    "_keys_draft",
    "_pilot_start",
    "_read_keys",
    "_reorder_slack",
    "_seconds",
    "_weigher",
    "bisect",
    "container_of",
    "contextlib",
    "dataclass",
    "ffmpeg_pack_command",
    "film_keys",
    "forget_playing",
    "grid_for",
    "hashlib",
    "head_open",
    "hls_dir",
    "json",
    "mapped_start",
    "mark",
    "mark_playing",
    "math",
    "os",
    "pack_origin",
    "pack_start",
    "parse_manifest",
    "playing_flag",
    "pull_head",
    "replace",
    "subprocess",
    "tempfile",
    "threading",
    "time",
    "urllib",
    "warm_at",
    "warm_file",
]

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.stream_core import (
        _SEEK_LOCK,
        _SEEK_OK,
        AUDIO_BITRATE,
        AUDIO_CHANNELS,
        AUDIO_CODEC,
        HEAD_OPEN,
        HEAD_OPEN_DEFAULT,
        KEYS_KEPT,
        KEYS_LOCK,
        KEYS_WAIT,
        PACK_LIST,
        PLAYING_FLAG,
        SEEK_SHIFT,
        SPLIT_SLACK,
        WARM_TIMEOUT,
    )
    from torrcast.stream_probe import _touch, _trim, segment_name


import bisect
import contextlib
import hashlib
import json
import math
import os
import subprocess
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from torrcast import InfraError
from torrcast.stream_core import (
    _ORIGIN,
    _ORIGIN_LOCK,
    AUDIO_PRIMING,
    HEAD_WARM,
    HLS_SEGMENT_SECONDS,
    MAX_SEGMENT_BYTES,
    PILOT_TIMEOUT,
)
from torrcast.timing import mark

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


@dataclass(frozen=True, slots=True)
class Grid:
    """Сетка сегментов: **абсолютные** границы, отсчитанные от нуля фильма.

    Это ответ на главную грабельку нарезки. Раньше сетка была не сеткой, а шагом:
    ffmpeg резал каждые N секунд от первого пакета своего прогона, а прогон начинался там,
    куда увёл ``-ss``, — то есть на опорном кадре не позже нужного места. Поэтому имя
    сегмента врало о содержимом до длины GOP, а **фаза** сетки после каждой перемотки
    становилась другой. Место фильма при одной фазе игралось чисто, при другой — вешало
    приёмник, и воспроизвести это можно было только случайно.

    Здесь граница — это число, а не «сколько прошло от старта упаковки»: сегмент ``k``
    занимает ``[bounds[k], bounds[k+1])`` всегда, с какого бы места ни начали паковать.
    Ровно этот список идёт и в манифест (``EXTINF`` = фактическая длина куска), и в
    команду ffmpeg (:func:`ffmpeg_pack_command`), так что манифест и нарезка — одно и то же.

    Границы стоят на **опорных кадрах**, когда карта их известна (:mod:`torrcast.keymap`):
    тогда каждый сегмент декодируется сам по себе, и перемотка в любую точку показывает
    картинку сразу, а не с ближайшего опорного кадра где-то в середине куска. Нет карты —
    ровная сетка по :data:`HLS_SEGMENT_SECONDS`, как было.
    """

    #: Начала сегментов, секунды от начала фильма; ``bounds[0]`` всегда 0.
    bounds: tuple[float, ...]
    duration: float
    #: Границы стоят на опорных кадрах - сегменты самостоятельны.
    on_keys: bool = False
    #: Предсказатель веса куска ``[a, b)`` КОПИЕЙ - без потолка перекодирования
    #: (:func:`_weigher`), по той же карте опорных кадров, по которой поставлены
    #: границы; ``None`` - карты нет, и вес куска неизвестен. Хранится в сетке, потому
    #: что карта известна ровно в момент её постройки, а нужна позже и в другом месте:
    #: прогрев проверяет по ней бюджет диска (:meth:`torrcast.warm.Warmer._forecast`).
    weigh: Callable[[float, float], float] | None = None
    #: Начало ленты: на столько секунд вперёд сдвинуты ВСЕ метки, которые мы пакуем из
    #: этого файла (:func:`pack_origin`). Ноль - метки и есть время фильма.
    #:
    #: Число живёт в сетке ровно по той же причине, что и :attr:`weigh`: оно одно на весь
    #: фильм, известно в момент постройки сетки, а нужно позже и в трёх разных местах -
    #: живой упаковке, прогреву и перекоду. Отдельным параметром его пришлось бы протащить
    #: до каждого из них, и первый же забытый вызов вернул бы дефект: заход, упаковавший
    #: без сдвига, ставит на стыке с чужим ход меток НАЗАД.
    origin: float = 0.0

    @classmethod
    def uniform(cls, duration: float, step: float = HLS_SEGMENT_SECONDS) -> Grid:
        """Ровная сетка: каждые ``step`` секунд от нуля фильма.

        Хвост короче половины шага отдельным сегментом не делается — он прилипает к
        последнему: пара секунд в манифесте лишним куском не стоит. Кино короче шага —
        один сегмент на всё, и длительность остаётся честной: приписать ему лишние
        секунды значило бы пообещать приёмнику то, чего в файле нет.
        """
        length = max(duration, 0.0)
        count = max(1, math.ceil((length - step / 2) / step))
        return cls(tuple(step * k for k in range(count)), length, False)

    @classmethod
    def on_keyframes(
        cls,
        keys: Sequence[float],
        duration: float,
        step: float = HLS_SEGMENT_SECONDS,
        sizes: Sequence[int] = (),
        extra_mbit: float = 0.0,
        ceiling_mbit: float = 0.0,
        cap: float = MAX_SEGMENT_BYTES,
        fixed_mbit: float = 0.0,
        origin: float = 0.0,
    ) -> Grid:
        """Сетка по опорным кадрам: следующая граница — первый опорный кадр не раньше,
        чем через ``step`` секунд после предыдущей, **и не тяжелее**
        :data:`MAX_SEGMENT_BYTES`. Для первых двух границ берётся ближайший кадр с
        любой стороны от ``step``.

        Голова - исключение из общего правила: на «Моане» 2016 прежняя сетка выбирала
        14.890 вместо ближайших 9.927 с дважды подряд; живой Q70D молча закрывал
        медиасессию после этой головы. Дальше остаётся первый кадр после ``step``: так
        сцена-вспышка (много опорных кадров подряд) не дробит весь манифест, а правила
        весового потолка сохраняют прежний выбор.

        **Потолок байт** — вторая половина правила, и она главная:
        приёмник Q70D срывается в BUFFERING на сегменте тяжелее ~19 МБ, сколько бы секунд
        в нём ни было. Поэтому граница берётся так: первый опорный кадр не раньше ``step``,
        **если** предсказанный вес куска влезает в ``cap``; не влезает — последний кадр,
        который влезает (кусок получается короче ``step``, и это дешевле подвиса); не влезает
        ни один — первый кадр, что есть (резать GOP нельзя, и врать об этом не будем).

        Вес предсказывается из той же карты, из которой строится профиль тяжести
        (:class:`torrcast.recode.Weights`): ``sizes`` — смещения опорных кадров в файле,
        ``extra_mbit`` — что в контейнере есть, а на ТВ не уезжает (лишние дорожки и
        субтитры), ``ceiling_mbit`` — потолок перекодирования: тяжёлый кусок уедет
        не тяжелее него. Карты смещений нет (кэш прошлой версии, чужой контейнер) — правило
        вырождается в прежнее «первый кадр не раньше ``step``».

        ``fixed_mbit`` — вес считается не по карте, а по нашему же битрейту: так весит
        кусок файла, который перекодируется целиком (:data:`RECODE_CODECS`).
        """
        weigh = _weigher(keys, sizes, extra_mbit, ceiling_mbit, fixed_mbit)
        # Отдельно от границ - вес КОПИИ (без потолков): тяжёлый кусок режется сеткой и
        # уезжает на ТВ перекодом, а на диск прогрев кладёт сначала его самого, во весь
        # вес. Бюджет прогрева проверяется именно под этот, пиковый, вес.
        copy = (
            _weigher(keys, sizes, extra_mbit, 0.0)
            if len(sizes) == len(keys) and len(keys) >= 2
            else None
        )
        bounds = [0.0]
        limit = duration - step / 2
        index = 0
        while True:
            prev = bounds[-1]
            index = bisect.bisect_right(keys, prev, lo=index)
            fits = before = first = None
            for key in keys[index:]:
                if key >= limit:
                    break
                if weigh(prev, key) <= cap:
                    fits = key
                if key >= prev + step:
                    first = key
                    break
                if key - prev >= step / 2 and weigh(prev, key) <= cap:
                    before = key
            if first is None:
                if weigh(prev, duration) <= cap:
                    break  # короткий хвост влезает и по-прежнему прилипает к последнему
                tail = [key for key in keys[index:] if prev < key < duration]
                tail_fits = [key for key in tail if weigh(prev, key) <= cap]
                if not tail:
                    break  # последний GOP тяжелее потолка, резать его нечем
                bounds.append(tail_fits[-1] if tail_fits else tail[0])
                continue
            first_fits = weigh(prev, first) <= cap
            nearest_head = (
                len(bounds) <= 2
                and before is not None
                and first_fits
                and prev + step - before < first - prev - step
            )
            if nearest_head:
                assert before is not None  # условие nearest_head уже доказало границу
                bounds.append(before)
            elif first_fits or fits is None:
                bounds.append(first)  # влез - или один GOP тяжелее потолка, резать нечем
            else:
                bounds.append(fits)
        return cls(tuple(bounds), duration, True, copy, origin)

    @property
    def count(self) -> int:
        return len(self.bounds)

    def start(self, slot: int) -> float:
        """Начало сегмента, секунды от начала фильма."""
        return self.bounds[min(max(slot, 0), self.count - 1)]

    def end(self, slot: int) -> float:
        """Конец сегмента: начало следующего, а у последнего — конец фильма."""
        return self.bounds[slot + 1] if 0 <= slot + 1 < self.count else self.duration

    def span(self, slot: int) -> float:
        return self.end(slot) - self.start(slot)

    def slot_at(self, seconds: float) -> int:
        """Номер сегмента, в который попадает секунда фильма."""
        return max(0, bisect.bisect_right(self.bounds, max(seconds, 0.0)) - 1)

    def after(self, seconds: float) -> float:
        """Начало сегмента, который идёт ЗА тем, куда попадает ``seconds``.

        Ровно то место, куда обязан целиться прыжок через кусок, на котором приёмник
        споткнулся (:meth:`torrcast.cast.ChromecastReceiver._nudge`): прыжок короче
        сегмента приземляется в него же и перешагнуть его не может никогда. Сегменты
        разной длины (6.0-14.9 с на «Моане» 2016), поэтому шаг тут и не может быть
        числом - только границей сетки.
        """
        return self.end(self.slot_at(seconds))

    def target(self) -> int:
        """``EXT-X-TARGETDURATION``: округлённая вверх длина самого длинного сегмента."""
        return max(1, math.ceil(max(self.span(k) for k in range(self.count))))

    def manifest(self) -> str:
        """Манифест VOD на **весь фильм**: все сегменты сетки и ``ENDLIST``.

        Приёмнику неоткуда узнать длительность, кроме
        манифеста: у скользящего live-плейлиста её нет вовсе, поэтому ТВ считал показ
        эфиром и не давал ни таймлайна, ни перемотки. Здесь длительность — сумма
        ``EXTINF``, то есть ровно длина фильма, и перемотка разрешена в любую его точку.

        Манифест **статический**: он не зависит от того, что упаковано прямо сейчас, и
        перечисляет сегменты, которых на диске ещё нет. Целый фильм в tmpfs не влезает —
        но приёмнику и не нужен файл раньше, чем он его попросит: за это отвечает
        :class:`Feed`, которая на запрос неупакованного места пакует оттуда.

        Проверено на живом Q70D: ``duration`` в MEDIA_STATUS = длине манифеста,
        ``seek`` в произвольную точку отрабатывает за доли секунды и показ продолжается.
        """
        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            f"#EXT-X-TARGETDURATION:{self.target()}",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXT-X-PLAYLIST-TYPE:VOD",
        ]
        if self.on_keys:
            # Не украшение: каждый сегмент начинается с опорного кадра, и приёмнику
            # разрешено начать показ с любого - на этом и держится перемотка.
            lines.append("#EXT-X-INDEPENDENT-SEGMENTS")
        for slot in range(self.count):
            lines += [f"#EXTINF:{self.span(slot):.6f},", segment_name(slot)]
        lines.append("#EXT-X-ENDLIST")
        return "\n".join(lines) + "\n"


def _weigher(
    keys: Sequence[float],
    sizes: Sequence[int],
    extra_mbit: float,
    ceiling_mbit: float,
    fixed_mbit: float = 0.0,
) -> Callable[[float, float], float]:
    """Предсказатель веса куска ``[a, b)`` в байтах — тот же расчёт, что у профиля тяжести.

    Карта даёт байты **контейнера**: у «Моаны 2» это десять озвучек и восемь субтитров
    сверх картинки. На ТВ уезжает видео плюс наш AAC, поэтому из битрейта вычитается
    ``extra_mbit`` (:class:`torrcast.recode.Weights` считает ту же поправку), а тяжёлый
    кусок ещё и перекодируется — выше ``ceiling_mbit`` он не уедет при всём желании.

    Карты смещений нет — вес неизвестен, и предсказатель честно отдаёт ноль: правило
    потолка тогда не срабатывает ни разу, а сетка остаётся прежней.

    ``fixed_mbit`` карту не спрашивает вообще: при сплошном перекоде вес куска задаём
    мы сами, и вес источника к нему отношения не имеет. 🔴 Замер на живом Q70D
    (TC-29, «Bocchi the Rock» 1.3 Мбит/с HEVC): сетка поверила карте, поставила куски
    по 15-20 с, а перекод положил в них 18.3 и 21.4 МБ — при потолке 16 и замеренной
    границе срыва 19.4.
    """
    if fixed_mbit > 0:
        return lambda a, b: max(0.0, b - a) * fixed_mbit * 1e6 / 8
    if len(sizes) != len(keys) or len(keys) < 2:
        return lambda a, b: 0.0

    def weigh(a: float, b: float) -> float:
        span = b - a
        if span <= 0:
            return 0.0
        head = bisect.bisect_right(keys, a + SPLIT_SLACK) - 1
        tail = bisect.bisect_right(keys, b + SPLIT_SLACK) - 1
        head = min(max(head, 0), len(sizes) - 1)
        tail = min(max(tail, 0), len(sizes) - 1)
        mbit = max(0.0, (sizes[tail] - sizes[head]) * 8 / span / 1e6 - extra_mbit)
        if ceiling_mbit > 0:
            mbit = min(mbit, ceiling_mbit)
        return mbit * span * 1e6 / 8

    return weigh


def _keys_cache(source_url: str) -> Path:
    """Где лежит снятая карта опорных кадров этого файла.

    Ключ — сам URL потока: в нём hash раздачи и номер файла, то есть ровно то, что
    определяет содержимое. Кэш нужен не ради экономии трафика (4 МБ), а ради времени:
    Cues лежат в хвосте файла, и **первое** чтение этого места стоит роя — замерено
    13.8 с на «Моане» 2016 и 24.4 с на «Моане 2». Второй показ
    того же файла (продолжение с середины — обычное дело) платить это не должен.
    """
    from torrcast.state import state_path

    return (
        state_path().parent / "keys" / f"{hashlib.sha1(source_url.encode()).hexdigest()[:16]}.json"
    )


class FilmKeys(NamedTuple):
    """Карта опорных кадров файла в том виде, в каком ей пользуется показ.

    ``at`` — времена от начала фильма, по ним строится сетка (:class:`Grid`).
    ``offset`` — где эти кадры лежат в файле; по ним греется рой под перемотку и под
    продолжение с середины (:func:`warm_at`). Списки одной длины, и порядок
    у них общий: ``at[k]`` лежит на ``offset[k]``.
    """

    duration: float
    at: list[float]
    offset: list[int]
    #: Контейнер файла, ``mkv`` или ``mp4``. Пусто - карта из кэша прошлой версии.
    kind: str = ""

    def byte_at(self, seconds: float) -> int:
        """Смещение опорного кадра не позже ``seconds``; карта без смещений — ``0``.

        Не позже, а не «ближайший»: показ с этого места и начнёт читать, потому что
        ffmpeg с ``-ss`` встаёт на опорный кадр не позже запрошенного.
        """
        if not self.offset:
            return 0
        found = bisect.bisect_right(self.at, max(seconds, 0.0)) - 1
        return self.offset[min(max(found, 0), len(self.offset) - 1)]


def _read_keys(cache: Path) -> FilmKeys | None:
    with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
        saved = json.loads(cache.read_text("utf-8"))
        at = [float(x) for x in saved["keys"]]
        # Кэш прошлой версии смещений не знал: он всё ещё годен для сетки, а грелка
        # позиции без смещений просто не работает - это лучше, чем выбросить карту.
        ready = FilmKeys(
            float(saved["duration"]),
            at,
            [int(x) for x in saved.get("bytes", ())],
            str(saved.get("kind", "")),
        )
        _touch(cache)  # полка живёт по времени обращения (:func:`_trim`)
        return ready
    return None


def _fetching(lock: Path) -> bool:
    """Карту прямо сейчас снимает кто-то другой (прогрев под меню — соседний процесс)."""
    with contextlib.suppress(OSError):
        return time.time() - lock.stat().st_mtime < KEYS_LOCK
    return False


def _keys_draft(cache: Path) -> Path:
    """Черновик кэша карты - свой у каждого писателя.

    Замок на карту берётся не всегда (протух, каталог только для чтения), а на одно имя
    два писателя пишут вперемешку - и ``replace`` выложил бы наружу склейку двух половин.
    """
    return cache.with_suffix(f".{os.getpid()}-{threading.get_ident()}.tmp")


def _hold_keys_lock(lock: Path, done: threading.Event) -> None:
    """Держать замок карты живым, пока его хозяин работает: трогать mtime до ``done``."""
    while not done.wait(KEYS_LOCK / 3):
        with contextlib.suppress(OSError):
            lock.touch()


def film_keys(source_url: str) -> FilmKeys:
    """Карта опорных кадров видео: из кэша или из индекса контейнера (:mod:`torrcast.keymap`).

    Если карту уже снимает прогрев (:func:`warm_file`), ждём его, а не читаем индекс
    файла вторым потоком: рой от этого быстрее не станет, а старт показа удвоится.
    """
    from torrcast.keymap import keyframes, video_track

    cache = _keys_cache(source_url)
    if (ready := _read_keys(cache)) is not None:
        mark("карта: из кэша")
        return ready
    lock = cache.with_suffix(".lock")
    deadline = time.monotonic() + KEYS_WAIT
    waited = time.monotonic()
    while _fetching(lock) and time.monotonic() < deadline:
        time.sleep(0.2)
        if (ready := _read_keys(cache)) is not None:
            mark("карта: дождались прогрева", ждали=round(time.monotonic() - waited, 2))
            return ready
    with contextlib.suppress(OSError):
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.touch()
    mark("карта: чтение")
    # Замок живёт по mtime (:func:`_fetching`), поэтому его надо освежать, пока держим:
    # чтение хвоста у холодного роя стоит 2-6 с, но разбор карты добавляет к ним секунды,
    # и на длинном фильме замок протух бы прямо под работающим читателем - а сосед,
    # увидевший протухший замок, полез бы читать тот же хвост вторым потоком.
    holding = threading.Event()
    keeper = threading.Thread(target=_hold_keys_lock, args=(lock, holding), daemon=True)
    keeper.start()
    # ⚠️ Замок снимается не после чтения, а после **записи кэша**: между ними лежит разбор
    # карты, и сосед, отпущенный раньше времени, кэша ещё не увидит и полезет читать хвост
    # сам. Ровно так холодный старт платил разбор дважды (замер: CLI и юнит
    # разбирали одну и ту же карту параллельно).
    try:
        found = keyframes(source_url)
        mark("карта: снята", кадров=len(found.points), байт=found.taken)
        # ⚠️ Дорожку видео выбираем ОДИН раз. Пока этот вызов стоял внутри списка, он
        # считался на каждую точку Cues, а сам он линейный по всем точкам - то есть карта
        # разбиралась квадратично. Цена замерена: «Моана 2», 7274
        # точки - 18.5 с чистого процессора после того, как рой всё отдал. Ровно это и
        # принимали за «первое чтение хвоста у холодного роя»: рой отдаёт
        # Cues за 2-6 с, остальное было наше.
        track = video_track(found.points)
        video = [p for p in found.points if p.track == track]
        ready = FilmKeys(
            found.duration, [p.at for p in video], [p.offset for p in video], found.kind
        )
        with contextlib.suppress(OSError):
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = _keys_draft(cache)
            body = {
                "duration": ready.duration,
                "keys": ready.at,
                "bytes": ready.offset,
                "kind": ready.kind,
            }
            try:
                tmp.write_text(json.dumps(body), "utf-8")
                tmp.replace(cache)
            finally:  # своё имя не должно превратиться в свой же мусор на полке
                tmp.unlink(missing_ok=True)
        # Подрезка идёт после записи, а не до: только что снятая карта - самая свежая на
        # полке, и подрезать раньше значило бы мерить полку без неё.
        _trim(cache.parent, KEYS_KEPT)
    finally:
        holding.set()
        with contextlib.suppress(OSError):
            lock.unlink(missing_ok=True)
    return ready


def warm_at(source_url: str, offset: int, upto: int = HEAD_WARM, alive: Any = None) -> int:
    """Протянуть через рой кусок файла с ``offset`` и выбросить: нужен прогретый кэш.

    Показ читает файл ровно двумя местами: начало (заголовок контейнера, а с ним и
    ``moov`` у mp4) и то место, откуда пойдёт картинка. Пока этих байт нет в кэше
    TorrServer, ffmpeg ждёт рой, а показ ждёт ffmpeg. Под меню они берутся за время,
    пока человек отвечает.
    Лишнего трафика тут нет — ровно эти байты показ прочитает следующим действием.

    ``alive`` — жив ли ещё смысл греть: релиз, от которого показ отказался, дотягивать
    нельзя, он отъедает полосу у выбранного (:meth:`torrcast.cli._Bench.keep_only`).
    """
    began = time.monotonic()
    taken = 0
    where = f"bytes={offset}-{offset + upto - 1}"
    request = urllib.request.Request(source_url, headers={"Range": where})
    with urllib.request.urlopen(request, timeout=WARM_TIMEOUT) as answer:
        while chunk := answer.read(1 << 20):
            taken += len(chunk)
            if alive is not None and not alive():
                break
    mark("прогрето", смещение=offset, байт=taken, за=round(time.monotonic() - began, 2))
    return taken


def pull_head(source_url: str, upto: int = HEAD_WARM, alive: Any = None) -> int:
    """Прогреть начало файла — частный случай :func:`warm_at` со смещением ноль."""
    return warm_at(source_url, 0, upto, alive)


def head_open(kind: str) -> int:
    """Сколько головы греть под продолжение с середины: у mkv её мало, у mp4 там ``moov``."""
    return HEAD_OPEN.get(kind, HEAD_OPEN_DEFAULT)


def container_of(name: str) -> str:
    """Контейнер по имени файла раздачи; чужое расширение — пустая строка.

    Нужно ровно для одного: карта, снятая прошлой версией, лежит в кэше без контейнера, и
    без этой подсказки продолжение по такому фильму грело бы восемь мегабайт головы до
    конца времён. Имя файла у показа под рукой всегда — оно приезжает вместе со списком
    раздачи, — а сам URL потока имени не несёт (в нём hash и номер файла).
    """
    tail = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if tail in {"mkv", "webm"}:
        return "mkv"
    return "mp4" if tail in {"mp4", "m4v", "mov"} else ""


def warm_file(source_url: str, at: float = 0.0, alive: Any = None, name: str = "") -> None:
    """Прогреть файл фоном: карта опорных кадров, начало потока и место, откуда играем.

    Зовётся с самой ранней секунды, когда известен файл, — пока человек отвечает на
    вопросы. Порядок именно такой: без карты показ не построит сетку и не
    запустит ffmpeg вовсе; начало файла нужно ffmpeg, чтобы вообще открыть вход; а место
    ``at`` — это то, что он прочитает третьим. Не вышло — не беда: показ сделает то же
    самое сам, просто на своём времени.

    ``at > 0`` — продолжение с середины. Там начало файла нужно только на
    заголовок, поэтому его берём куском поменьше (:data:`HEAD_OPEN`, размер зависит от
    контейнера), а основной прогрев уходит туда, где лежит позиция: байтовое смещение
    известно из той же карты.
    """

    def work() -> None:
        keys: FilmKeys | None = None
        with contextlib.suppress(Exception):
            keys = film_keys(source_url)
        if alive is not None and not alive():
            return
        offset = keys.byte_at(at) if keys is not None and at > 0 else 0
        # Контейнер знает карта; у карты из кэша прошлой версии его нет - тогда спрашиваем
        # имя файла раздачи, оно у показа всегда под рукой.
        head = head_open((keys.kind if keys is not None else "") or container_of(name))
        with contextlib.suppress(Exception):
            pull_head(source_url, head if offset else HEAD_WARM, alive)
        if not offset:
            return
        with contextlib.suppress(Exception):
            if alive is None or alive():
                warm_at(source_url, offset, HEAD_WARM, alive)

    threading.Thread(target=work, daemon=True).start()


def grid_for(
    source_url: str,
    duration: float,
    step: float = HLS_SEGMENT_SECONDS,
    on_keys: bool = True,
    say: Any = None,
    delivered_mbit: float = 0.0,
    ceiling_mbit: float = 0.0,
    fixed_mbit: float = 0.0,
    cap: float = MAX_SEGMENT_BYTES,
) -> Grid:
    """Сетка для конкретного файла: по опорным кадрам, если карту удалось снять.

    Карта берётся двумя-тремя Range-запросами из индекса контейнера
    (:func:`torrcast.keymap.keyframes`) и стоит около секунды. Контейнер незнакомый, индекса
    в нём нет, карта не похожа на видео — берём ровную сетку и говорим об этом вслух:
    молчаливая подмена нарезки — ровно то, из-за чего подвис приёмника расследовали
    двое суток.

    ``delivered_mbit`` — сколько Мбит/с уедет на ТВ в среднем по фильму (паспорт ffprobe,
    :attr:`Media.delivered_mbit`), ``ceiling_mbit`` — потолок перекодирования
    (:attr:`torrcast.state.Config.recode_mbit`, ноль — перекодирование выключено). Из них
    считается поправка «контейнер → ТВ» и работает потолок веса сегмента
    (:data:`MAX_SEGMENT_BYTES`) — без них правило потолка вырождается в прежнее.

    ``cap`` — потолок веса одного куска: он у каждого приёмника свой
    (:attr:`torrcast.profile.Profile.max_segment_bytes`), и умолчание тут осторожное.

    ``fixed_mbit`` — сплошной перекод (:data:`RECODE_CODECS`): вес сегмента больше не
    зависит от карты вовсе, потому что на ТВ уезжает не файл, а наш поток с известным
    битрейтом. Карта тут не просто лишняя, а вредная: лёгкий HEVC (1.3 Мбит/с) она
    объявляет лёгким и разрешает 20-секундные куски, а после перекода тот же кусок
    весит столько, сколько мы в него положили.
    """
    began = time.monotonic()
    # Начало ленты - свойство файла, а не способа его нарезать: считается до всякой развилки
    # и уезжает в любую сетку, какой бы из путей ниже ни выбрался (:func:`pack_origin`).
    origin = pack_origin(source_url)
    if not on_keys:
        if say:
            say(f"сетка ровно по {step:g} с - так велено настройкой")
        return replace(Grid.uniform(duration, step), origin=origin)
    try:
        found = film_keys(source_url)
    except InfraError as exc:
        if say:
            say(f"сетка ровно по {step:g} с: {exc}")
        return replace(Grid.uniform(duration, step), origin=origin)
    length = duration or found.duration
    if len(found.at) < 3 or found.at[-1] < length * 0.5:
        if say:
            say(f"сетка ровно по {step:g} с: карта опорных кадров не похожа на видео")
        return replace(Grid.uniform(length, step), origin=origin)
    grid = Grid.on_keyframes(
        found.at,
        length,
        step,
        sizes=found.offset,
        extra_mbit=_extra_mbit(found, delivered_mbit),
        ceiling_mbit=ceiling_mbit,
        fixed_mbit=fixed_mbit,
        cap=cap,
        origin=origin,
    )
    if say:
        spans = [grid.span(k) for k in range(grid.count)]
        say(
            f"сетка по опорным кадрам: {grid.count} сегментов по {min(spans):.1f}-"
            f"{max(spans):.1f} с, не тяжелее {cap / 1e6:.0f} МБ "
            f"(карта за {time.monotonic() - began:.1f} с)"
        )
    return grid


def _extra_mbit(keys: FilmKeys, delivered_mbit: float) -> float:
    """Что в контейнере есть, а на ТВ не уезжает, Мбит/с — по карте и паспорту.

    Ровно то же число, что набирает :meth:`torrcast.recode.Weights.calibrate` по факту, но
    известное до первого куска. Паспорт молчит (mp4 без тегов) — ноль: тогда потолок веса
    считает по контейнеру целиком, то есть режет с запасом. Запас безопасен, недооценка нет.
    """
    if delivered_mbit <= 0 or len(keys.offset) != len(keys.at) or len(keys.at) < 3:
        return 0.0
    span = keys.at[-1] - keys.at[0]
    if span <= 0:
        return 0.0
    container = (keys.offset[-1] - keys.offset[0]) * 8 / span / 1e6
    return max(0.0, container - delivered_mbit)


def mapped_start(keys: FilmKeys | None, at: float) -> float:
    """Куда встанет ffmpeg после ``-ss at`` — **по карте опорных кадров**. Не знаем — ``nan``.

    Гадания тут нет: перемотку ведёт тот же индекс контейнера, из которого снята карта
    (``Cues`` у mkv, ``stss`` у mp4), поэтому место посадки — это соседняя строка той же
    таблицы, а какая именно, решает демуксер (:data:`SEEK_SHIFT`). У mkv ffmpeg берёт
    строку **строго раньше** запрошенного времени (целимся в опорный кадр — уезжаем на
    предыдущий, то самое «через один» на «Моане» 2016: ``-ss 66.150`` → 62.688), у mp4 —
    строку не позже запрошенного, то есть при попадании в кадр стоит ровно на нём.

    ``nan`` отдаётся везде, где правило не обязано работать, и каждый случай стоит своих
    трёх строк:

    * контейнера нет в :data:`SEEK_SHIFT` (карта из кэша прошлой версии, .ts) — правила нет;
    * карта пустая или ``at`` за её краями — соседней строки просто не существует;
    * посадка приходится на самое начало файла — там ffmpeg не пускает dts ниже нуля и
      сдвигает метки на кадр-два вперёд (замер: карта обещает 0.000, факт 0.080), то есть
      единственное место, где карта права, а ffmpeg встаёт не по ней.

    ⚠️ Это предсказание, а не факт: пока оно не сверено с пробным прогоном на этом самом
    файле (:func:`pack_start`), верить ему нельзя. Резы захода муксер отмеряет от ПЕРВОГО
    ПАКЕТА, и ошибка на один опорный кадр разъезжает с сеткой весь заход целиком.
    """
    if keys is None or at <= 0:
        return math.nan
    shift = SEEK_SHIFT.get(keys.kind)
    if shift is None or len(keys.at) < 2:
        return math.nan
    # mkv садится строго раньше запрошенного, mp4 - не позже: разница ровно в том, куда
    # отнести попадание в сам кадр, и она же есть весь SEEK_SHIFT.
    index = bisect.bisect_right(keys.at, at + SPLIT_SLACK) - 1 + shift
    if index < 1 or index >= len(keys.at) or at > keys.at[-1]:
        return math.nan
    return keys.at[index]


def pack_start(
    source_url: str, at: float, timeout: float = PILOT_TIMEOUT, keys: FilmKeys | None = None
) -> float:
    """Куда на самом деле встанет ffmpeg после ``-ss at``: по карте, а иначе пробным прогоном.

    Знать это обязательно: сетка сегментного муксера отсчитывается от **первого пакета
    прогона**, а ``-ss`` уводит ffmpeg на опорный кадр не позже запрошенного места — причём
    не обязательно на ближайший (замерено на «Моане» 2016: ``-ss 66.150``, сама граница —
    опорный кадр, даёт первый кадр 62.688, то есть **через один**).

    Раньше это место каждый раз измеряли: тот же ffmpeg, тот же ``-ss``, один кадр на
    выход. Цена — 0.13 с на локальном файле и до 2.9 с на живой раздаче, и платил её каждый
    копирующий заход: старт показа, каждая перемотка, оба захода прогрева. Между тем карта
    опорных кадров к этому времени уже снята и лежит в кэше, а перемотку демуксера ведёт
    ровно она (:func:`mapped_start`) — то есть место посадки вычислимо.

    🔴 Но вычисленному верят **только после сверки с фактом**: предсказание проверяется
    пробным прогоном один раз на файл, и лишь потом заходы идут без него. Дешёвая
    «уверенность» тут уже дважды стоила показу правильных кусков — ошибка на один опорный
    кадр уводит все резы захода, и куски лежат под верными именами с чужим содержимым.
    Разошлось больше полукадра — файл помечается недоверенным навсегда, и по нему
    работает прежний пробный прогон.

    ``-muxdelay 0 -muxpreload 0`` обязательны: без них мультиплексор mpegts добавляет
    к меткам свои 1.4 с, и «первый кадр» оказался бы не там, где он есть на самом деле.
    """
    if at <= 0:
        return 0.0
    # Карту не ищем, а берём готовую: к первому заходу она уже снята и лежит в кэше (по ней
    # построена сетка). Нет её там - нет и предсказания, и работает прежний пробный прогон;
    # лезть за картой в рой ради экономии на пробном прогоне было бы обменом секунды на
    # секунды.
    if keys is None:
        with contextlib.suppress(Exception):
            keys = _read_keys(_keys_cache(source_url))
    guess = mapped_start(keys, at)
    if not math.isnan(guess):
        with _SEEK_LOCK:
            trusted = _SEEK_OK.get(source_url)
        if trusted:
            mark("заход по карте", просили=round(at, 3), встали=round(guess, 3))
            return guess
    found = _pilot_start(source_url, at, timeout)
    if not math.isnan(guess) and _SEEK_OK.get(source_url) is None:
        agreed = abs(found - guess) <= SPLIT_SLACK
        with _SEEK_LOCK:
            _SEEK_OK[source_url] = agreed
        mark(
            "сверка карты с прогоном",
            сошлось=agreed,
            карта=round(guess, 3),
            факт=round(found, 3),
        )
    return found


def _pilot_start(source_url: str, at: float, timeout: float = PILOT_TIMEOUT) -> float:
    """Пробный прогон в один кадр: где ffmpeg встал на самом деле. Не вышло — ``at``."""
    with tempfile.TemporaryDirectory(prefix="torrcast-pilot-") as tmp:
        probe_path = f"{tmp}/first.ts"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-copyts", "-ss", f"{at:.3f}",
            "-i", source_url, "-map", "0:v:0", "-c", "copy", "-frames:v", "1",
            "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-y", probe_path,
        ]  # fmt: skip
        try:
            subprocess.run(command, capture_output=True, timeout=timeout, check=True)
            found = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                 "packet=pts_time", "-of", "csv=p=0", "-read_intervals", "%+#1", probe_path],
                capture_output=True, text=True, timeout=timeout, check=True,
            )  # fmt: skip
        except (OSError, subprocess.SubprocessError):
            return at  # не вышло - считаем, что встали ровно на границе, и скажем об этом
        head = found.stdout.strip().splitlines()
        try:
            return float(head[0].split(",")[0])
        except (IndexError, ValueError):
            return at


def pack_origin(source_url: str, timeout: float = PILOT_TIMEOUT) -> float:
    """На сколько вперёд сдвигается вся лента этого фильма, секунды. Считается раз на файл.

    🔴 Ровно тут рождался обратный ход меток на ПЕРВОМ стыке - тот, на котором приёмник
    бросал разбор (``Parsed buffers not in DTS sequence`` → ``pipeline_error 16``) и показ
    умирал молча, два запуска из пяти.

    Механизм (замерено, а не выведено). Начало фильма лежит НИЖЕ нуля: у релиза с
    B-кадрами первый пакет видео идёт с ``dts = pts - задержка перестановки`` (замер на
    ролике: pts 0.000, dts -0.083), а наш звук вдобавок начинается на набивку кодировщика
    раньше (:data:`AUDIO_PRIMING`). Отрицательных меток mpegts не выражает, и муксер
    двигает их сам - но двигает **каждый файл отдельно**, потому что сегментный муксер
    открывает под каждый кусок свой mpegts. Первому куску сдвиг нужен, соседнему уже нет:
    v0 уезжает на ленте «время фильма + сдвиг», v1 - на честном времени фильма, и на их
    стыке метки идут НАЗАД. Дальше все стыки чистые, поэтому дефект и жил только на первом.
    Замер на ролике: v0 DTS 0.000..7.958 против v1 DTS 7.917.., откат -0.042 с; куски при
    этом честные, ни одного общего кадра у них нет - назад идут только метки.

    ``-avoid_negative_ts disabled`` от этого не спасает и никогда не спасал: он снимает
    сдвиг с ВНЕШНЕГО, сегментного муксера, а внутренние mpegts его не наследуют вовсе
    (сегментный копирует им ``max_delay``, но не ``avoid_negative_ts``) - и сдвиг просто
    переезжает внутрь, из «одного на прогон» становясь «своим у каждого куска».

    Лечится это единственным способом: **лента фильма одна на все заходы**. Сдвиг
    называется явно (``-output_ts_offset``), считается один раз на файл и уезжает в каждый
    заход - живой упаковки, прогрева, перекода. Тогда ни одному муксеру двигать нечего
    (метки уже выше нуля), первый кусок ничем не отличается от прочих, а заход из середины
    после ``-ss`` встаёт с тем же началом ленты, что и заход от нуля. Проверено обоими
    концами: заход с нуля и заход после ``-ss`` дают на одном и том же куске
    **побайтово те же метки**.

    Считается сдвиг с запасом и намеренно: переоценка стоит нескольких лишних миллисекунд
    начала на всей ленте разом (ни один потребитель абсолютных меток такой разницы не
    видит), недооценка возвращает дефект целиком. Слагаемых два - задержка перестановки
    видео и набивка нашего звука, - и берётся не большее из них, а сумма: какое из двух
    окажется ниже нуля первым, решает порядок чередования потоков, а не мы.

    Не прочли (файл не открылся, ffprobe не дожил) - остаётся набивка звука: гадать про
    видео нечем, а мёртвый вход всё равно не упакуется.
    """
    with _ORIGIN_LOCK:
        ready = _ORIGIN.get(source_url)
    if ready is not None:
        return ready
    delay = _reorder_slack(source_url, timeout)
    # Вверх до миллисекунды: в команду сдвиг уезжает с тремя знаками, и округление вниз
    # оставило бы метки на доли миллисекунды ниже нуля - то есть вернуло бы муксеру повод
    # сдвинуть первый кусок самому.
    origin = math.ceil(((delay or 0.0) + AUDIO_PRIMING) * 1000.0) / 1000.0
    with _ORIGIN_LOCK:
        origin = _ORIGIN.setdefault(source_url, origin)
    mark("начало ленты", сдвиг=origin, померено=delay is not None)
    return origin


def _reorder_slack(source_url: str, timeout: float = PILOT_TIMEOUT) -> float | None:
    """На сколько метки начала фильма уходят ниже нуля, секунды; ``None`` - не прочли.

    Спрашивается ОДИН ffprobe и сразу тремя способами, потому что ни один из трёх не
    работает на всех контейнерах:

    * ``pts - dts`` первых пакетов - прямой ответ там, где dts в файле есть (mp4: замер на
      ролике - pts 0.000 при dts -0.080);
    * ``-dts`` тех же пакетов - на случай, когда лента начинается ниже нуля сама по себе,
      а не из-за перестановки;
    * ``has_b_frames / кадров в секунду`` - **единственный** ответ для mkv, где dts не
      хранится вовсе. Замер на живой раздаче: у первых двух пакетов ``dts_time`` = ``N/A``,
      и первые два способа молчат, а ffmpeg тем временем достраивает те же dts сам и
      уводит начало ниже нуля ровно на эту величину.

    Берётся наибольшее из трёх: переоценка стоит миллисекунд, недооценка возвращает дефект
    (:func:`pack_origin`). Читается голова файла и только она (``-read_intervals``) - то,
    что к этому времени уже прогрето (:func:`pull_head`).
    """
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-read_intervals", "%+#4",
        "-show_entries", "stream=has_b_frames,avg_frame_rate:packet=pts_time,dts_time",
        "-of", "json", source_url,
    ]  # fmt: skip
    try:
        found = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True)
        payload = json.loads(found.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    slack = [0.0]
    for number, packet in enumerate(payload.get("packets") or []):
        if not isinstance(packet, dict):
            continue
        pts, dts = _seconds(packet.get("pts_time")), _seconds(packet.get("dts_time"))
        if dts is None:
            continue
        slack.append(-dts)
        # ⚠️ ``pts - dts`` считается ТОЛЬКО у первого пакета: ниже нуля лента уходит ровно
        # на его перестановку. У пакетов в середине эта разница - глубина перестановки
        # вообще (замер на живой раздаче: 0.167 с у третьего пакета против 0.083 у начала,
        # а по фильму она доходит до 0.417), и брать её значило бы сдвигать ленту фильма
        # на полсекунды там, где хватает двух кадров.
        if number == 0 and pts is not None:
            slack.append(pts - dts)
    for stream in payload.get("streams") or []:
        if not isinstance(stream, dict):
            continue
        rate = _seconds(stream.get("avg_frame_rate", "0/0"))
        depth = stream.get("has_b_frames")
        if rate and rate > 0 and isinstance(depth, int) and depth > 0:
            slack.append(depth / rate)
    return max(slack)


def _seconds(raw: Any) -> float | None:
    """Число из поля ffprobe: секунды или дробь ``24/1``; ``None`` - поля нет или ``N/A``."""
    if not isinstance(raw, str):
        return None
    head, _, tail = raw.partition("/")
    try:
        return float(head) / float(tail) if tail else float(head)
    except (ValueError, ZeroDivisionError):
        return None


def ffmpeg_pack_command(
    source_url: str,
    audio_index: int,
    run_dir: str,
    grid: Grid,
    slot: int,
    at: float,
    readrate: float = 1.0,
    burst: float = 0.0,
    encode: Any = None,
    until: int = -1,
) -> list[str]:
    """Команда ffmpeg: паковать фильм по сетке ``grid``, начиная с сегмента ``slot``.

    ``at`` — где прогон встанет на самом деле (:func:`pack_start`). Всё держится на трёх
    вещах:

    * ``-f segment -segment_times`` вместо ``-f hls -hls_time``. Сегментный муксер умеет
      получить **список** мест реза, а не один шаг, — и это единственный способ положить
      границы туда, где они стоят в манифесте. Список считается от ``at``, потому что
      муксер сравнивает метки с начала прогона, а не с начала фильма.
    * ``-copyts`` **вместе с** ``-muxdelay 0 -muxpreload 0 -avoid_negative_ts disabled`` —
      метки времени остаются исходными, то есть абсолютным временем фильма. Без
      ``-copyts`` ffmpeg сбрасывает их в ноль на каждом ``-ss``, и приёмник после
      перепаковки показывал бы позицию от начала куска, а не от начала фильма. А одного
      ``-copyts`` мало: мультиплексор mpegts по умолчанию сдвигает ВСЕ метки вперёд на
      ``muxdelay + muxpreload`` = **1.4 с**
      (:data:`MPEGTS_MUX_DELAY`), и «время фильма» в сегментах оказывалось не временем
      фильма. Цена этой мелочи — двое суток чужого расследования: карту
      опорных кадров сверяли с метками готовых сегментов, видели ровно +1.400 с на каждой
      границе и записали это в «карта врёт про этот релиз». Карта не врала — врал муксер,
      и :func:`pack_start` эти же два флага ставил с самого начала, то есть пробный прогон
      мерил время фильма, а настоящий писал время фильма плюс 1.4 с.
    * ``-avoid_negative_ts disabled`` **вместе с** ``-output_ts_offset`` (:attr:`Grid.origin`)
      — и порознь они не работают. Первый запрещает двигать метки внешнему, сегментному
      муксеру; сам по себе он ничего не лечит, потому что внутренние mpegts (по одному на
      кусок!) его не наследуют и двигают начало каждый за себя — сдвинутым оказывается
      ровно первый кусок, и на стыке со вторым метки идут НАЗАД
      (🔴 :func:`pack_origin`, разбор целиком там же). Второй поднимает всю ленту фильма
      выше нуля заранее и одинаково во всех заходах, так что двигать становится нечего
      никому: и заход от нуля, и заход после ``-ss`` пишут на одном и том же куске
      побайтово те же метки.
    * ``-break_non_keyframes`` — резать ли посреди GOP. На сетке по опорным кадрам этого
      не нужно и нельзя: муксер сам дождётся опорного кадра, и граница встанет ровно туда,
      куда обещал манифест. На ровной сетке — наоборот, иначе куски разъедутся с сеткой.

    Прогон почти всегда начинается раньше своей границы: ``-ss`` уводит на опорный кадр
    раньше. Эта докатка уходит в отдельный сегмент с номером ``slot - 1``, который
    :meth:`Packer.publish` выбрасывает, — так наружу попадает только то, что совпадает
    с манифестом, и чужой сегмент не затирается.

    Темп упаковки держится **одним ffmpeg'ом и без пауз процесса**:

    * ``-readrate 1`` — читать вход со скоростью реального времени. Придержать упаковку
      сигналом (SIGSTOP) больше не нужно: она сама не убегает дальше ``burst``.
    * ``-readrate_initial_burst`` (ffmpeg ≥ 6.1) — первые ``burst`` секунд читаются на
      полной скорости. Без него ``readrate 1`` дважды вреден: приёмник идёт вровень с
      упаковкой и буферится на каждом стыке, а после перемотки ему разом нужны шесть
      сегментов (замерено на Q70D: v50…v55 за одну секунду).

    Отставание ffmpeg наверстывает сам: его планка — ``wallclock * readrate + burst``, и
    пока текущий dts ниже планки, он читает на полной скорости (``readrate_sleep`` в
    fftools). То есть просадка роя лечится без нашего участия, а запас впереди приёмника
    остаётся ограниченным ``burst`` — ровно поэтому tmpfs не растёт без предела.

    ``encode`` (:class:`torrcast.recode.Encode`) заменяет ``-c:v copy`` перекодированием
    тяжёлого куска. Всё остальное — сетка, метки, границы, звук — остаётся тем же,
    иначе стык копии с перекодом приёмник бы заметил.

    ⚠️ У перекодирующего прогона **докатки нет**: ``-ss`` при перекодировании точен, лишние
    кадры декодируются и выбрасываются, так что первый пакет стоит ровно на границе. Звать
    для него :func:`pack_start` не надо (и вредно: измеренный ``at`` уведёт весь прогон на
    сегмент назад).

    ``until`` ограничивает прогон сегментом с этим номером — кодировщик работает заходами
    по несколько кусков, чтобы перемотка успевала переприоритезировать очередь.
    """
    run = run_dir.rstrip("/")
    behind = encode is None and at < grid.start(slot) - SPLIT_SLACK  # прогон начался раньше границы
    first = slot if behind else slot + 1
    upto = grid.count if until < 0 else min(until + 2, grid.count)
    times = ",".join(f"{grid.start(k) - at:.3f}" for k in range(first, upto))
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]
    if readrate > 0:
        command += ["-readrate", f"{readrate:g}"]
        if burst > 0:
            command += ["-readrate_initial_burst", f"{burst:g}"]
    command += ["-copyts"]
    if slot > 0:
        command += ["-ss", f"{grid.start(slot):.3f}"]
    command += ["-i", source_url, "-map", "0:v:0", "-map", f"0:a:{audio_index}"]
    command += ["-c:v", "copy"] if encode is None else encode.args(grid, slot, upto - 2)
    if until >= 0:
        # ``-to`` при ``-copyts`` считается в абсолютном времени фильма - том же, что в
        # сетке. Без ограничения заход кодировщика доехал бы до конца фильма.
        command += ["-to", f"{grid.end(until) + 1.0:.3f}"]
    # ⚠️ Аргументы собираются СПИСКОМ, а не строкой с последующим ``.split()``. Разбиение по
    # пробелам разрывало надвое любой путь с пробелом внутри (каталог прогона задаёт человек
    # через ``TORRCAST_STATE``), и ffmpeg получал вместо имени списка два огрызка: список
    # нарезки не появлялся вовсе, :meth:`Packer.publish` не выкладывал наружу ничего, а
    # показ видел только «ни куска» - без причины.
    if grid.origin > 0:
        # 🔴 Начало ленты - одно на все заходы фильма (:func:`pack_origin`). Без него метки
        # начала уходят ниже нуля, mpegts их не выражает, и муксер двигает их сам - но у
        # сегментного муксера свой mpegts на КАЖДЫЙ кусок, поэтому сдвигается ровно первый,
        # а на стыке со вторым метки идут назад. Сдвиг стоит ЗДЕСЬ, а не в резах: резы
        # муксер меряет от первого пакета прогона, то есть на них он не влияет вовсе, а
        # ``-to`` считается в метках входа, до сдвига.
        command += ["-output_ts_offset", f"{grid.origin:.3f}"]
    command += [
        "-c:a", AUDIO_CODEC, "-ac", f"{AUDIO_CHANNELS}", "-b:a", AUDIO_BITRATE,
        "-muxdelay", "0", "-muxpreload", "0", "-avoid_negative_ts", "disabled",
        "-f", "segment", "-segment_format", "mpegts",
        "-segment_time_delta", f"{SPLIT_SLACK:g}",
        "-break_non_keyframes", f"{0 if grid.on_keys else 1}",
        "-segment_start_number", f"{slot - 1 if behind else slot}",
        "-segment_list", f"{run}/{PACK_LIST}",
        "-segment_list_type", "csv", "-segment_list_flags", "+live",
    ]  # fmt: skip
    if times:
        command += ["-segment_times", times]
    command.append(f"{run}/v%d.ts")
    return command


def parse_manifest(text: str) -> tuple[list[tuple[str, float]], bool]:
    """Манифест → пары (сегмент, длительность) и признак конца (``#EXT-X-ENDLIST``)."""
    segments: list[tuple[str, float]] = []
    seconds = 0.0
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            with contextlib.suppress(ValueError):
                seconds = float(line[8:].split(",")[0])
        elif line and not line.startswith("#"):
            segments.append((line, seconds))
    return segments, "#EXT-X-ENDLIST" in text


def hls_dir(path: str) -> Path:
    """Чистый каталог сегментов. Это tmpfs: фильм на диск не пишем."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    for junk in (*directory.glob("v*.ts"), *directory.glob("*.m3u8")):
        junk.unlink(missing_ok=True)
    forget_playing(directory)  # флажок прошлого показа картинку нового не доказывает
    return directory


def playing_flag(out: Path) -> Path:
    """Путь флажка «картинка на экране» (:data:`PLAYING_FLAG`)."""
    return out / PLAYING_FLAG


def mark_playing(out: Path) -> None:
    """Показ увидел ``PLAYING``: с этой секунды на экране есть изображение."""
    with contextlib.suppress(OSError):
        playing_flag(out).touch()


def forget_playing(out: Path) -> None:
    """Убрать флажок: следующий показ обязан доказать картинку заново."""
    with contextlib.suppress(OSError):
        playing_flag(out).unlink(missing_ok=True)
