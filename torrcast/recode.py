"""Динамический битрейт: тяжёлые куски фильма перекодируются заранее (§6.2 SPEC-v2).

Зачем. Q70D срывается в BUFFERING на сегментах примерно с 15 Мбит/с и выше (§7.5), и до
06-08 это лечилось отбором: честный тяжёлый 1080p просто не брали. Владелец такое решение
отменил — «лучше чтобы всегда и везде было 1080». Значит тяжесть надо снимать не отбором,
а перекодированием, и только там, где она есть.

Как это вообще возможно без ребуферов. Три факта, каждый замерен на стенде 06-08-2026:

1. **Профиль тяжести известен со старта.** Карта опорных кадров (:mod:`torrcast.keymap`)
   несёт время и абсолютное смещение каждого опорного кадра, то есть байты и секунды
   КАЖДОГО сегмента сетки — до того, как упакован хоть один. Считается это из уже снятой
   карты, то есть даром.
2. **Байты карты — это контейнер целиком, а на ТВ уезжает только видео и одна дорожка.**
   У «Моаны 2» (13.3 ГБ) десять звуковых дорожек и восемь субтитров: контейнер идёт
   19.2 Мбит/с, а на ТВ уезжает 15.1. Поправка постоянна (замер: 4.0…4.3 Мбит/с на восьми
   сегментах подряд), поэтому она **вычитается** — и уточняется по факту первых же
   выложенных сегментов (:meth:`Weights.calibrate`).
3. **Кодировать успеваем.** libx264 на 4 vCPU E5-2696 v4, 1080p, кап 12–13 Мбит/с:
   ``veryfast`` — 1.54× реального времени, ``superfast`` — 2.62×, ``ultrafast`` — 4.36×
   (замер `scripts/recodebench.py`). Тяжёлого в «Моане 2» 46 % фильма, и модель показа
   (тот же скрипт, ключ ``--plan``) говорит: при 1.54× опаздывает ОДИН сегмент из 192 —
   ``v0``, тяжёлый с нулевой секунды, до которого фора не набирается ни при какой скорости.

⚠️ Грабля, стоившая отладки: при ``-c:v copy`` ffmpeg по ``-ss`` встаёт на опорный кадр
**раньше** запрошенного и докатывает до границы (§6.0), а при перекодировании тот же
``-ss`` работает точно — лишние кадры декодируются и выбрасываются. То есть у
перекодирующего прогона докатки нет вовсе, и ``at`` равен границе сетки ровно. Первая
версия честно мерила ``at`` пробным прогоном, как для копии, и весь прогон уезжал ровно на
один сегмент: ``v359`` содержал место ``v360``.

⚠️ Вторая грабля: ``-force_key_frames`` сравнивает время кадра с запрошенным как есть, а
граница печатается с тремя знаками. Округление вверх (4909.9167 → «4909.917») уводило
опорный кадр на следующий, и на стыке копии с перекодом терялся один кадр. Поэтому
принудительные опорные кадры просятся на :data:`torrcast.stream.SPLIT_SLACK` раньше границы
— ровно тот же допуск, с которым режет сегментный муксер.
"""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.stream import FilmKeys, Grid

__all__ = [
    "PRESETS",
    "RECODE_DIR",
    "Encode",
    "Recoder",
    "Weights",
    "preset_for",
]

#: Каталог перекодированных кусков внутри каталога показа. Наружу они попадают не отсюда,
#: а через :meth:`torrcast.stream.Packer.publish` — выкладка сегментов остаётся ровно в
#: одном месте кода, и инвариант «край двигает только состоявшееся переименование» (§7.4)
#: не размывается вторым выкладывающим.
RECODE_DIR: Final = "recode"

#: Пресеты libx264 и их скорость в разах от реального времени. Замер на стенде CT501
#: (4 vCPU E5-2696 v4, 1080p 1920×960, кап 12/13 Мбит/с, вход 23.7 Мбит/с): ultrafast
#: 4.36×, superfast 2.62×, veryfast 1.54×, faster 1.04×, fast 0.72×, medium 0.55×.
#: Здесь числа занижены примерно на 10 %: планировать по замеру «в идеальных условиях»
#: нельзя, рядом работает упаковщик и TorrServer.
PRESETS: Final = (("veryfast", 1.40), ("superfast", 2.35), ("ultrafast", 3.90))

#: Насколько раньше границы просится принудительный опорный кадр (см. вторую граблю выше).
_KEY_SLACK: Final = 0.02

#: Сколько сегментов берём за один заход кодировщика. Ограничение не по мощности, а по
#: отзывчивости: перемотка обязана переприоритезировать очередь, а бросить можно только
#: заход целиком.
RUN_MAX: Final = 6

#: Приоритет процессу кодировщика. Упаковщик (копия + AAC) и TorrServer должны получать
#: процессор раньше него: их работа привязана к реальному времени, а кодировщик работает
#: впрок и опоздание на секунду ему ничего не стоит.
NICE: Final = 15

#: Приоритет захода за ГОЛОВОЙ прогона (:meth:`Recoder.opening`). Голова — исключение из
#: правила выше: её ждёт не запас впрок, а сам старт показа, и каждая её секунда — это
#: секунда чёрного экрана. Замер на стенде («Моана 2» 13.3 ГБ, v0 длиной 19.96 с,
#: ultrafast): под ``nice 15`` — 8.05 с, под ``nice 0`` — 5.84 с.
HEAD_NICE: Final = 0


@dataclass(frozen=True, slots=True)
class Encode:
    """Чем перекодировать тяжёлый кусок: то же разрешение, тот же кодек, ниже битрейт."""

    preset: str = "veryfast"
    #: Целевой битрейт, Мбит/с. Умолчание и его замер — :attr:`torrcast.state.Config.recode_mbit`.
    mbit: float = 9.0

    @property
    def maxrate(self) -> float:
        """Потолок мгновенного битрейта. Выше цели на 8 % — иначе кап душит движение."""
        return self.mbit * 1.08

    def args(self, grid: Grid, slot: int, until: int) -> list[str]:
        """Аргументы видео для :func:`torrcast.stream.ffmpeg_pack_command`.

        Принудительные опорные кадры стоят на границах сетки — без них сегментный муксер
        с ``-break_non_keyframes 0`` ждал бы ближайший кадр кодировщика и резал бы куда
        попало, а обещание ``EXT-X-INDEPENDENT-SEGMENTS`` в манифесте стало бы враньём.
        """
        keys = ",".join(
            f"{grid.start(k) - _KEY_SLACK:.3f}" for k in range(slot, min(until + 2, grid.count))
        )
        return [
            "-c:v", "libx264",
            "-preset", self.preset,
            "-b:v", f"{self.mbit:.2f}M",
            "-maxrate", f"{self.maxrate:.2f}M",
            "-bufsize", f"{self.mbit * 2:.2f}M",
            "-pix_fmt", "yuv420p",
            "-profile:v", "high",
            "-level", "4.1",
            "-sc_threshold", "0",
            "-force_key_frames", keys,
        ]  # fmt: skip


def preset_for(
    seconds: float, slack: float, presets: tuple[tuple[str, float], ...] = PRESETS
) -> str:
    """Самый качественный пресет, который успевает уложить ``seconds`` фильма в ``slack``.

    Не успевает ни один — берём самый быстрый: кратковременное снижение качества владелец
    разрешил, подгруз — нет. ``slack <= 0`` (кусок уже играют) — тоже самый быстрый.
    """
    for name, speed in presets:
        if slack > 0 and seconds / speed <= slack * 0.7:
            return name
    return presets[-1][0]


@dataclass(slots=True)
class Weights:
    """Профиль тяжести фильма: сколько Мбит/с уедет на ТВ в каждом сегменте сетки.

    Считается из карты опорных кадров до всякой упаковки. Байты карты — контейнер целиком,
    поэтому из них вычитается всё, что на ТВ не уезжает (:attr:`extra`), а само это число
    уточняется по факту (:meth:`calibrate`).
    """

    #: Мбит/с по контейнеру для каждого слота сетки.
    raw: tuple[float, ...]
    #: Что в контейнере есть, а на ТВ не уезжает: лишние дорожки и субтитры, Мбит/с.
    extra: float = 0.0
    #: Сколько замеров легло в :attr:`extra` (0 — только оценка по ffprobe).
    measured: int = 0

    @classmethod
    def of(cls, keys: FilmKeys, grid: Grid, extra: float = 0.0) -> Weights | None:
        """Профиль по карте и сетке. Карта без смещений (кэш прошлой версии) — ``None``."""
        if not keys.offset or len(keys.offset) != len(keys.at) or len(keys.at) < 3:
            return None
        raw: list[float] = []
        for slot in range(grid.count):
            span = grid.span(slot)
            head = keys.byte_at(grid.start(slot))
            tail = keys.byte_at(grid.end(slot))
            # У последнего сегмента следующей границы нет, и хвост файла картой не описан:
            # берём вес предыдущего. Один сегмент из полутысячи — цена честнее выдумки.
            if slot + 1 >= grid.count or tail <= head:
                raw.append(raw[-1] if raw else 0.0)
                continue
            raw.append((tail - head) * 8 / span / 1e6 if span > 0 else 0.0)
        return cls(raw=tuple(raw), extra=extra)

    def at(self, slot: int) -> float:
        """Сколько Мбит/с уедет на ТВ в сегменте ``slot``."""
        if not 0 <= slot < len(self.raw):
            return 0.0
        return max(0.0, self.raw[slot] - self.extra)

    def heavy(self, threshold: float) -> tuple[int, ...]:
        """Слоты, которые приёмник не потянет: ``threshold`` Мбит/с и выше."""
        return tuple(s for s in range(len(self.raw)) if self.at(s) >= threshold)

    def calibrate(self, slot: int, size: int, span: float) -> None:
        """Уточнить :attr:`extra` по реально выложенному сегменту-копии.

        Скользящее среднее: одиночный сегмент может соврать (дорожки в mkv лежат
        неравномерно), а десяток — уже нет. Замер 06-08 на восьми сегментах подряд дал
        разброс 3.97…4.26 Мбит/с при среднем 4.10.
        """
        if not 0 <= slot < len(self.raw) or span <= 0:
            return
        seen = size * 8 / span / 1e6
        gap = self.raw[slot] - seen
        # Здравый смысл: лишние дорожки не могут весить больше самого фильма. Всё, что
        # выходит за половину контейнера, — это не поправка, а перекодированный кусок или
        # обрезанный файл, и учиться на нём нельзя.
        if not 0.0 <= gap < self.raw[slot] * 0.5:
            return
        self.measured += 1
        weight = min(self.measured, 10)
        self.extra += (gap - self.extra) / weight


@dataclass(slots=True)
class Recoder:
    """Фоновый кодировщик тяжёлых кусков: работает впрок, пока играет остальное.

    Порядок работы — от места показа вперёд: ближайший тяжёлый кусок важнее дальнего, а
    перемотка меняет место показа и тем самым переприоритезирует очередь на следующем же
    заходе. Готовый кусок ложится в :data:`RECODE_DIR` и ждёт там своего часа; наружу его
    выкладывает упаковщик, когда дойдёт до этого места (:meth:`Packer.publish`).
    """

    source: str
    audio: int
    grid: Grid
    spare: Path
    weights: Weights
    threshold: float = 15.0
    encode: Encode = field(default_factory=Encode)
    #: Горизонт: дальше этого места фильма впрок не работаем. Ограничение не по времени, а
    #: по tmpfs — готовые куски лежат в памяти. Модель показа «Моаны 2»: 300 с горизонта
    #: держат пик кэша на 459 МБ и не стоят ни одного опоздания.
    ahead: float = 300.0
    #: Потолок кэша перекодированного, МБ. Достигнут — кодировщик спит, а не растёт.
    cache_mb: float = 384.0
    run_max: int = RUN_MAX
    #: Запас, с которым перекод обязан успеть, чтобы его стоило ждать (секунды).
    hold_guard: float = 2.0
    #: Сколько кодировщику отпущено на подъём первого захода. Пока он поднимается,
    #: упаковщик уже выкладывает ``burst`` — и без этой форы первые тяжёлые куски успевали
    #: уйти копией просто потому, что ffmpeg ещё не стартовал.
    grace: float = 6.0
    #: Во сколько секунд обходится подъём одного захода: ffmpeg открывает вход, TorrServer
    #: доезжает до нужного места. Замер на стенде — 1–3 с, берём верх.
    startup: float = 3.0
    #: Потолок ожидания перекода ПЕРВОГО сегмента прогона (:meth:`opening`), секунды.
    #: Умолчание и его замер — :attr:`torrcast.state.Config.recode_head_wait`.
    head_wait: float = 12.0
    log: Any = None

    #: Где сейчас показ; обновляет :func:`torrcast.cli._hold`.
    played: float = 0.0
    #: Докуда дошла упаковка — последний выложенный наружу сегмент (:meth:`note`).
    #:
    #: ⚠️ Срок готовности считается от НЕЁ, а не от места показа, и это не мелочь.
    #: Упаковщик идёт впереди показа на ``burst`` (60 с) и на старте выкладывает эти
    #: 60 секунд разом. Считай кодировщик срок по показу — и он спокойно взялся бы за
    #: заход на полторы минуты, пока упаковщик уже выложил тяжёлые куски как есть.
    #: Ровно это и было видно в первом прогоне: v361 и v362 (26 и 28 Мбит/с) ушли копией,
    #: потому что кодировщик считал, что до них ещё полторы минуты.
    edge: int = -1
    #: Первый сегмент текущего прогона упаковки — тот, с которого пойдёт картинка
    #: (:meth:`opening`). ``-1`` — упаковка ещё не начиналась.
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
    thread: Any = None
    packer: Any = None
    lock: Any = field(default_factory=threading.Lock)

    @property
    def targets(self) -> tuple[int, ...]:
        """Тяжёлые слоты — те, что приёмник не потянет как есть."""
        return self.weights.heavy(self.threshold)

    def start(self) -> None:
        """Поднять поток кодировщика. Тяжёлых кусков нет — не поднимать вовсе."""
        if not self.targets:
            self._say("тяжёлых кусков нет — перекодировать нечего")
            return
        heavy = self.targets
        share = sum(self.grid.span(s) for s in heavy) / max(self.grid.duration, 1.0)
        self._say(
            f"тяжёлых кусков {len(heavy)} из {self.grid.count} "
            f"({share * 100:.0f}% фильма, порог {self.threshold:.0f} Мбит/с) — "
            f"перекодирую заранее в {self.encode.mbit:.0f} Мбит/с"
        )
        self.spare.mkdir(parents=True, exist_ok=True)
        self.began = time.monotonic()
        self.thread = threading.Thread(target=self._work, daemon=True, name="torrcast-recode")
        self.thread.start()

    def stop(self) -> None:
        """Снять кодировщик и его процесс. Готовые куски не трогаем — их уберёт показ."""
        self.stopped = True
        with self.lock:
            packer, self.packer = self.packer, None
        if packer is not None:
            packer.stop(keep_files=True, reason="показ окончен")

    def ready(self, slot: int) -> Path | None:
        """Путь к готовому перекодированному куску или ``None``."""
        from torrcast.stream import segment_name

        path = self.spare / segment_name(slot)
        return path if path.exists() else None

    def opening(self, slot: int) -> None:
        """Упаковка начинается заново с сегмента ``slot`` (:meth:`torrcast.stream.Feed.restart`).

        Зовётся на старте показа, на возврате с паузы и на каждой перемотке. Делает три
        вещи, и все три нужны ровно ради первого сегмента (§6.2):

        * помечает ``slot`` головой прогона — только его копию можно придержать, пока
          картинки ещё нет (:meth:`holding`);
        * отматывает :attr:`edge` назад: наружу этот прогон не выложил ещё ничего, а
          старое значение осталось от прошлого места показа и заставило бы :meth:`_pick`
          пропустить саму голову (после перемотки назад — весь остаток фильма);
        * ставит :attr:`played` на начало этого сегмента. Место показа приходит в
          кодировщик раз в две секунды (:func:`torrcast.cli._hold`), и на перемотке оно
          столько же врёт — а очередь кодировщика решается прямо сейчас.
        """
        self.head = slot
        self.head_at = time.monotonic()
        self.edge = slot - 1
        self.played = self.grid.start(slot)

    def _head_pending(self) -> bool:
        """Голова прогона тяжёлая, ещё не готова и её ещё ждут (:attr:`head_wait`)."""
        head = self.head
        if head < 0 or head in self.done or self.ready(head) is not None:
            return False
        if time.monotonic() - self.head_at >= self.head_wait:
            return False
        return head in set(self.targets)

    def holding(self, slot: int) -> bool:
        """Придержать ли копию этого куска ради перекода, который вот-вот будет готов.

        Правило одно и оно про срок, а не про расстояние: ждать стоит ровно тогда, когда
        перекод успеет **раньше**, чем показ дойдёт до этого места. Плоский порог «держим
        всё, что дальше N секунд» тут не работает в обе стороны — живой прогон на Q70D
        показал оба края: v359 (26 Мбит/с) при пороге 25 с не придержали, хотя кодировщику
        было нужно три секунды, а v360 придержали и отпустили раньше, чем заход дошёл до
        него, — и оба ушли копией, и оба уронили показ в BUFFERING.

        Кусок, до которого показ уже дошёл, не держим никогда: ожидание под носом у
        показа — это и есть подгруз. **Кроме одного** — головы прогона (:meth:`opening`):
        показ стоит ровно на ней, картинки ещё нет ни одного кадра, и ждать тут значит
        не подгружаться, а стартовать. Уйди голова копией — приёмник встаёт на первой же
        секунде показа в тяжёлом месте (старт, «Продолжить?», перемотка). Ожидание
        ограничено :attr:`head_wait` и стоит ровно один ultrafast-сегмент (2.3–3.6 с).
        """
        now = time.monotonic()
        # Перекод уже лежит — держать нечего, :meth:`Packer.publish` возьмёт его сам.
        if self.ready(slot) is not None:
            return False
        if slot == self.head:
            return (
                self.head_wait > 0
                and now - self.head_at < self.head_wait
                and slot in set(self.targets)
            )
        left = self.grid.start(slot) - self.played
        if left <= 0:
            return False
        job = self.job
        if job is None:
            # Заход не идёт: кодировщик либо ещё поднимается (первый раз), либо стоит
            # МЕЖДУ заходами — и то и другое секунды, а не минуты.
            #
            # ⚠️ Раньше тут стоял отказ по истечении :attr:`grace`, и он стоил живого
            # прогона: заход за головой длился 8 с при форе 6 с, а очередь идёт от места
            # показа вперёд — то есть следующим кодировщик взялся бы ровно за этот кусок.
            # В журнале это выглядело как «тяжёлый v359 (26 Мбит/с) ушёл копией: заход
            # не идёт», а на экране — как 16 опросов BUFFERING из 34.
            if slot not in set(self.targets):
                return False
            warm = max(self.startup, self.grace - (now - self.began))
            return self.grid.span(slot) / PRESETS[-1][1] + warm + self.hold_guard <= left
        first, last, until, since, speed = job
        if slot < first or now >= until:
            return False
        if slot <= last:
            todo = sum(self.grid.span(k) for k in range(first, slot + 1)) / speed - (now - since)
            return max(0.0, todo) + self.hold_guard <= left
        # Кусок ЗА текущим заходом. Раньше тут стоял отказ — и он честно стоил живого
        # прогона: заход за головой берёт один кусок (:meth:`_pick`), а упаковщик за эти
        # пять секунд успевал выложить копией три следующих тяжёлых. Считаем так же, как
        # внутри захода: кодировщику остаётся доделать этот заход, а дальше он пойдёт
        # самым быстрым пресетом — до срока ему деваться некуда.
        # Дальше следующего захода (:data:`RUN_MAX`) планов у кодировщика нет, и гадать
        # за него нельзя: там всё решит перемотка, потолок кэша и срок соседей.
        if slot > last + self.run_max or slot not in set(self.targets):
            return False
        rest = sum(self.grid.span(k) for k in range(first, last + 1)) / speed - (now - since)
        rest += sum(self.grid.span(k) for k in range(last + 1, slot + 1)) / PRESETS[-1][1]
        return max(0.0, rest) + self.hold_guard <= left

    def note(self, slot: int, recoded: bool) -> None:
        """Сегмент ушёл наружу: уточнить профиль по факту и посчитать опоздания.

        Копия — это единственный честный замер «сколько на самом деле уезжает на ТВ»:
        по ней и правится поправка :attr:`Weights.extra`, из-за которой байты карты
        (контейнер целиком) не равны байтам сегмента (видео и одна дорожка).
        """
        # Не максимум, а именно последний: перемотка назад начинает упаковку заново, и
        # край обязан уехать назад вместе с ней — иначе кодировщик решит, что всё позади
        # уже выложено, и до конца показа не возьмётся ни за один кусок.
        self.edge = slot
        if recoded:
            return
        with contextlib.suppress(OSError):
            size = (self.spare.parent / f"v{slot}.ts").stat().st_size
            self.weights.calibrate(slot, size, self.grid.span(slot))
        # Куски позади показа не в счёт: после перемотки прошлый прогон дописывает то,
        # что уже никто не увидит, и считать это опозданием — врать себе в отчёте.
        if slot in set(self.targets) and self.grid.end(slot) >= self.played:
            self.late += 1
            # Тяжёлый кусок, ушедший копией, — это будущий BUFFERING, и разбирать его
            # задним числом по размеру файла в журнале раздачи слишком дорого: пишем
            # сразу, чем в этот момент был занят кодировщик и куда смотрел показ.
            job = self.job
            self._say(
                f"тяжёлый v{slot} ({self.weights.at(slot):.0f} Мбит/с) ушёл копией: "
                f"показ {self.played:.0f} с, край {self.edge}, "
                + (f"заход v{job[0]}…v{job[1]}" if job else "заход не идёт")
            )

    def report(self) -> str:
        """Одна строка итога: сколько успели, сколько тяжёлых ушло как есть."""
        if not self.targets:
            return ""
        return (
            f"перекодировано {self.made} кусков ({self.seconds:.0f} с фильма), "
            f"тяжёлых ушло как есть {self.late}"
        )

    # ------------------------------------------------------------------ внутреннее

    def _say(self, text: str) -> None:
        if self.log is not None:
            self.log(text)

    def _weight(self) -> float:
        total = 0
        for path in self.spare.glob("v*.ts"):
            with contextlib.suppress(OSError):
                total += path.stat().st_size
        return total / 1e6

    def _sweep(self) -> None:
        """Выбросить готовые куски позади показа: их час прошёл, tmpfs не резиновый."""
        from torrcast.stream import segment_slot

        behind = self.grid.slot_at(max(0.0, self.played - 30.0))
        for path in self.spare.glob("v*.ts"):
            slot = segment_slot(path.name)
            if 0 <= slot < behind:
                path.unlink(missing_ok=True)
                self.done.discard(slot)

    def slack(self, slot: int) -> float:
        """Сколько секунд осталось до того, как этот кусок понадобится наружу.

        Считается от упаковщика, а не от показа: наружу сегмент выкладывает он, и опоздать
        к нему — значит выпустить тяжёлый кусок как есть (см. :attr:`edge`).
        """
        reached = self.grid.end(self.edge) if self.edge >= 0 else self.played
        return self.grid.start(slot) - max(self.played, reached)

    def _pick(self) -> tuple[int, int] | None:
        """Ближайший заход: подряд идущие тяжёлые куски, ещё не готовые и ещё успеваемые.

        Заход не растягивается дальше, чем кодировщик успеет: каждый следующий кусок
        обязан быть готов раньше, чем до него дойдёт упаковщик, — иначе длинный заход
        сам себе и создаёт опоздание.
        """
        # Считать от края упаковки, а не от показа: то, что уже выложено, перекодировать
        # поздно — приёмник это либо забрал, либо заберёт из tmpfs.
        here = max(self.grid.slot_at(self.played), self.edge + 1)
        horizon = self.played + self.ahead
        heavy = set(self.targets)
        quickest = PRESETS[-1][1]
        first = None
        for slot in sorted(heavy):
            if slot < here or self.grid.start(slot) > horizon:
                continue
            if slot in self.done or self.ready(slot) is not None:
                continue
            first = slot
            break
        if first is None:
            return None
        # Голова прогона идёт заходом в один кусок — и потому самым быстрым пресетом
        # (:func:`preset_for` от нулевого срока). Возьми её в общий заход — срок считался
        # бы по последнему куску, вышел бы superfast, и голова была бы готова к 4-5-й
        # секунде вместо 2-3-й. Остальное подхватит следующий заход.
        if first == self.head:
            return first, first
        last = first
        spent = self.grid.span(first) / quickest
        while (
            last + 1 in heavy
            and last + 1 - first + 1 <= self.run_max
            and last + 1 not in self.done
            and self.ready(last + 1) is None
        ):
            spent += self.grid.span(last + 1) / quickest
            if spent > self.slack(last + 1):
                break
            last += 1
        return first, last

    def _work(self) -> None:
        while not self.stopped:
            try:
                self._sweep()
                job = self._pick()
                if job is None:
                    time.sleep(1.0)
                    continue
                # Потолок кэша голову прогона не касается: её ждёт показ, а не запас
                # впрок, и уснуть тут значит отдать первый сегмент копией.
                if job[0] != self.head and self._weight() >= self.cache_mb:
                    time.sleep(2.0)
                    continue
                self._run(*job)
            # Кодировщик не имеет права ронять показ: он работает впрок, и его беда —
            # это в худшем случае тяжёлый кусок, ушедший как есть, а не конец фильма.
            except Exception as exc:
                self._say(f"перекодирование сорвалось ({exc}) — показ идёт как есть")
                time.sleep(5.0)

    def _run(self, first: int, last: int) -> None:
        from torrcast.stream import Packer, ffmpeg_pack_command

        seconds = sum(self.grid.span(s) for s in range(first, last + 1))
        # Срок — у ПОСЛЕДНЕГО куска захода: до него кодировщик доберётся позже всех, и
        # именно он решает, каким пресетом идти всему заходу.
        preset = preset_for(seconds, self.slack(last))
        encode = Encode(preset=preset, mbit=self.encode.mbit)
        # ⚠️ Пробного прогона тут нет и быть не должно: перекодирующий ffmpeg встаёт по
        # ``-ss`` точно, докатки не делает, и ``at`` равен границе сетки ровно.
        command = ffmpeg_pack_command(
            self.source,
            self.audio,
            str(self.spare / "run"),
            self.grid,
            first,
            self.grid.start(first),
            readrate=0.0,
            burst=0.0,
            encode=encode,
            until=last,
        )
        command = ["nice", "-n", str(HEAD_NICE if first == self.head else NICE), *command]
        began = time.monotonic()
        # Срок, до которого упаковщику имеет смысл придерживать копии этого захода:
        # вдвое больше ожидаемого да ещё десять секунд сверху. Просрочен — копия уходит
        # как есть, потому что подгруз хуже тяжёлого куска.
        speed = dict(PRESETS).get(preset, PRESETS[-1][1])
        with self.lock:
            self.packer = packer = Packer.start(command, self.spare, self.spare / "run", first)
            self.job = (first, last, began + seconds / speed * 2.0 + 10.0, began, speed)
        try:
            while not self.stopped:
                packer.publish()
                if packer.edge >= last or packer.poll() is not None:
                    break
                # Перемотали за пределы этого захода — он больше не самый нужный.
                gone = self.played > self.grid.end(last)
                far = self.played < self.grid.start(first) - self.ahead
                if gone or far:
                    packer.stop(keep_files=True, reason="перемотка")
                    return
                # Голова нового прогона важнее любого запаса впрок: её ждёт чёрный экран,
                # а всё остальное — только tmpfs. Доработать заход и потом взяться за
                # голову значит проесть её ожидание чужой работой: замер на стенде —
                # заход за `v0` (7 с) съедал ровно столько же от ожидания `v358`.
                if self._head_pending() and not first <= self.head <= last:
                    packer.stop(keep_files=True, reason="голова прогона важнее")
                    return
                time.sleep(0.3)
        finally:
            with self.lock:
                self.packer = None
                self.job = None
            packer.stop(keep_files=True, reason="заход окончен")
        # ⚠️ Считаем по краю СВОЕГО упаковщика, а не по тому, что осталось в каталоге:
        # готовый кусок оттуда уже мог забрать показ (:meth:`Packer.publish`), и глоб
        # каталога честный заход объявлял бы провалившимся. Ровно так «перекодировал v0»
        # печаталось как «не дало ни куска за 7 с» — и стоило часа отладки не там.
        got = list(range(first, min(last, packer.edge) + 1))
        self.done.update(got)
        self.made += len(got)
        self.seconds += sum(self.grid.span(s) for s in got)
        spent = time.monotonic() - began
        if got:
            self._say(
                f"перекодировал v{first}…v{first + len(got) - 1} "
                f"({seconds:.0f} с фильма за {spent:.0f} с, {preset})"
            )
        else:
            self._say(f"перекодирование v{first}…v{last} не дало ни куска за {spent:.0f} с")
            # Чтобы не крутиться на одном и том же месте вечно.
            self.done.update(range(first, last + 1))
