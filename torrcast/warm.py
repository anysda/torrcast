"""Прогрев показа на диск: весь фильм заранее, чтобы обрыв связи его не убил.

Показ живёт окном в tmpfs (:class:`torrcast.stream.Feed`), и это окно упирается в
сеть: пропал интернет — упаковке нечего читать, и через минуту на экране пусто.
Прогрев закрывает ровно эту дыру: фоном, на остатке процессора, весь фильм
докачивается и (где надо) перекодируется **на диск**, теми же именами той же сетки.
Добежал прогрев до конца — дальше показ и перемотки идут вообще без сети.

Три вещи, на которых всё держится:

* **сетка детерминирована.** Сегмент ``vN.ts`` — это всегда одно и то же место фильма,
  с какого бы места ни начали паковать (:class:`torrcast.stream.Grid`). Поэтому
  прогретый кусок и живой кусок взаимозаменяемы: показ берёт тот, который есть
  (:meth:`torrcast.stream.Feed.segment`);
* **прогретое лежит на диске, а не в tmpfs.** Целый фильм в памяти контейнера не
  помещается: 9 Мбит/с × 3 ч — это 12–13 ГБ, а вся RAM — 8 ГиБ. Живое окно остаётся
  в ``/dev/shm``, как было;
* **прогрев не имеет права мешать показу.** Он идёт ``nice`` и в темпе, который
  задан :attr:`Warmer.rate`, а когда запас живого показа проседает — встаёт
  (``SIGSTOP``) и ждёт. Приоритет всегда у того места, где смотрят прямо сейчас.

⚠️ **Один показ — один прогон ffmpeg.** Кадровая сетка AAC отсчитывается от ``-ss``
прогона, поэтому стык двух прогонов — это дыра до 21 мс в звуке, за которую Q70D
платит 2–5 секундами пересборки синхронизации (докстринг
:func:`torrcast.stream.merge_tracks`). Отсюда и устройство прогрева: не «заходы по N
кусков», а один прогон от места показа до конца фильма, который на просадке запаса
**замирает**, а не перезапускается. Второй прогон бывает ровно один — на голову
фильма, когда показ начат с середины, и его стык лежит там, где стык прогонов есть
и в живом показе.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import signal
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from torrcast.timing import mark

if TYPE_CHECKING:
    from torrcast.stream import Grid

__all__ = ["Vault", "Warmer", "warm_key", "warm_root"]

#: Каталог прогретого по умолчанию. Диск, не tmpfs - и это весь смысл модуля.
WARM_DIR: Final = "/var/lib/torrcast/warm"
#: ``TORRCAST_WARM=<каталог>`` - куда греть вместо настроенного места. Того же рода
#: переопределение, что ``TORRCAST_STATE`` и ``TORRCAST_CONFIG``: тестовый прогон не имеет
#: права ни писать в боевое хранилище, ни вытеснять из него чужое по бюджету.
WARM_ENV: Final = "TORRCAST_WARM"
#: Бюджет диска под всё прогретое, байты. 20 ГБ: худший случай одного показа - 3 ч на
#: потолке 9 Мбит/с, это ~12.8 ГБ, то есть один фильм влезает всегда, а второй вытесняет
#: первый по давности (:meth:`Vault.fit`).
WARM_BUDGET: Final = 20 << 30
#: Сколько места на диске не трогаем ни при каких обстоятельствах, байты. Бюджет считается
#: по нашим же файлам, а рядом живут чужие: упереть раздел в ноль прогревом нельзя.
FREE_FLOOR: Final = 3 << 30
#: Во сколько раз быстрее реального времени читает прогрев. Не «во весь опор»: прогрев
#: тянет из того же TorrServer, что и живая упаковка, и полная скорость отбирала бы у неё
#: и полосу, и кэш раздачи. Вчетверо - это 24-минутная серия за 6 минут и двухчасовой
#: фильм за полчаса, при этом живому окну остаётся втрое больше полосы, чем оно берёт.
WARM_RATE: Final = 4.0
#: ``nice`` прогрева: перекодирование впрок не имеет права отобрать процессор у показа.
WARM_NICE: Final = 19
#: Запас живого показа, ниже которого прогрев замирает, секунды.
GUARD_LOW: Final = 25.0
#: Запас, выше которого замерший прогрев оживает сразу. Разведены с :data:`GUARD_LOW`
#: намеренно: без гистерезиса прогрев дёргался бы стоп/старт на каждом опросе.
GUARD_HIGH: Final = 45.0
#: Сколько запас держится **над** :data:`GUARD_LOW`, прежде чем замерший прогрев оживает,
#: не дождавшись :data:`GUARD_HIGH`, секунды. Нужно ровно для тесного, но здорового показа:
#: когда смотрят вплотную за упаковкой, запас плавает у :data:`GUARD_LOW` и до
#: :data:`GUARD_HIGH` не дотягивает никогда - без этой поблажки прогрев голодал бы вечно и
#: "прогрета целиком" не наступало бы, а следующая серия так и не бралась в работу
#: (:meth:`Warmer._chain`). Отмеряем именно ВЫДЕРЖКУ над порогом стопа, а не разовое
#: касание: показ должен доказать, что запас и правда восстановился, а не мигнул. При
#: реально просевшем запасе (ниже :data:`GUARD_LOW`) выдержка обнуляется и прогрев стоит -
#: живой показ всегда важнее.
STARVE_GRACE: Final = 6.0
#: Сколько прогрев ждёт запаса живого показа, прежде чем начать работать несмотря ни на
#: что (:meth:`Warmer._wait_for_picture`), секунды.
START_GRACE: Final = 45.0
#: Файл-паспорт прогретого показа внутри его каталога.
META: Final = "warm.json"
#: Каталог прогона ffmpeg внутри каталога прогретого (см. :data:`torrcast.stream.PACK_DIR`).
RUN_DIR: Final = "run"


def warm_root(configured: str = WARM_DIR) -> Path:
    """Каталог прогретого с учётом :data:`WARM_ENV`."""
    return Path(os.environ.get(WARM_ENV) or configured or WARM_DIR)


def warm_key(source: str, audio: int, grid: Grid, encode: Any = None) -> str:
    """Ключ каталога прогретого: один и тот же показ — один и тот же ключ.

    В ключ входит всё, от чего зависит СОДЕРЖИМОЕ сегмента: раздача с номером файла
    (это уже есть в ``source``), звуковая дорожка, сетка и то, чем кодируем видео.
    Разошлось хоть что-то — ключ другой, и прогретое прошлого прогона не подсунется
    под чужие имена. Это дешевле и честнее, чем сверять паспорта: чужой каталог просто
    не находится, а его уберёт бюджет по давности.
    """
    parts = [
        source,
        f"a{audio}",
        f"g{grid.count}:{grid.duration:.3f}:{grid.on_keys:d}",
        "" if encode is None else f"e{encode.preset}:{encode.mbit:.2f}",
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class Vault:
    """Каталог прогретого одного показа и бюджет диска на всех.

    Читается отсюда напрямую: показ отдаёт приёмнику файл из этого каталога, не копируя
    его в tmpfs (:meth:`torrcast.stream.Feed.segment`). Копия стоила бы памяти ровно там,
    где её и не хватает.
    """

    root: Path
    key: str
    budget: int = WARM_BUDGET
    #: Сколько байт раздела не трогаем ни при каких обстоятельствах (:data:`FREE_FLOOR`).
    floor: int = FREE_FLOOR
    title: str = ""
    #: Чужие ключи, которые бюджет вытеснять не имеет права: серия, которую смотрят
    #: прямо сейчас, для прогрева следующей - чужой каталог (:meth:`fit`). Без этого
    #: прогрев следующей серии выедал бы текущую и обрыв связи убивал бы показ ровно
    #: там, где его и должно было спасти прогретое.
    keep: frozenset[str] = frozenset()

    @property
    def dir(self) -> Path:
        return self.root / self.key

    def path(self, slot: int) -> Path:
        from torrcast.stream import segment_name

        return self.dir / segment_name(slot)

    def have(self, slot: int) -> bool:
        return self.path(slot).exists()

    def slots(self) -> set[int]:
        """Что уже прогрето. Читается глобом: другого источника правды тут нет и не надо."""
        from torrcast.stream import segment_slot

        found: set[int] = set()
        with contextlib.suppress(OSError):
            for path in self.dir.glob("v*.ts"):
                slot = segment_slot(path.name)
                if slot >= 0:
                    found.add(slot)
        return found

    def open(self) -> None:
        """Завести каталог и паспорт. Паспорт нужен ровно бюджету: по его времени
        изменения считается давность показа (:meth:`fit`)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        self.touch()

    def touch(self) -> None:
        with contextlib.suppress(OSError):
            (self.dir / META).write_text(
                json.dumps({"key": self.key, "title": self.title, "at": time.time()}),
                encoding="utf-8",
            )

    def size(self) -> int:
        return _weigh(self.dir)

    def clear(self) -> None:
        """Показ досмотрен (или брошен насовсем) — прогретое стирается целиком."""
        shutil.rmtree(self.dir, ignore_errors=True)

    def free(self) -> int:
        """Сколько байт свободно на разделе прогрева."""
        try:
            stat = os.statvfs(self.root)
        except OSError:
            return 0
        return stat.f_bavail * stat.f_frsize

    def fit(self, need: int) -> str:
        """Место под ещё ``need`` байт: пусто — нашлось, иначе честная причина отказа.

        Бюджет один на всё прогретое, а не на показ: два фильма подряд не должны
        сложиться в сорок гигабайт. Вытесняются **чужие** каталоги, начиная с самого
        давнего, - свой не трогаем никогда, иначе прогрев съедал бы сам себя. Не свой,
        но и не чужой - :attr:`keep`: соседняя серия того же показа.

        Причин отказа две, и путать их нельзя: наш бюджет и чужое место на разделе.
        Рядом живут и состояние, и раздача, и система — упереть раздел в ноль прогревом
        не имеет права ни один бюджет.
        """
        mine = {self.key, *self.keep}
        others = sorted(
            (path for path in _dirs(self.root) if path.name not in mine),
            key=_touched,
        )
        while others and _weigh(self.root) + need > self.budget:
            shutil.rmtree(others.pop(0), ignore_errors=True)
        if need > self.budget - _weigh(self.root):
            return f"бюджет диска {self.budget / 1e9:.0f} ГБ исчерпан"
        if need + self.floor > self.free():
            return f"на разделе свободно {self.free() / 1e9:.1f} ГБ - это последний запас"
        return ""


def _dirs(root: Path) -> list[Path]:
    try:
        return [path for path in root.iterdir() if path.is_dir()]
    except OSError:
        return []


def _touched(path: Path) -> float:
    try:
        return (path / META).stat().st_mtime
    except OSError:
        return 0.0


def _weigh(where: Path) -> int:
    total = 0
    with contextlib.suppress(OSError):
        for path in where.rglob("v*.ts"):
            with contextlib.suppress(OSError):
                total += path.stat().st_size
    return total


@dataclass(slots=True)
class Warmer:
    """Фоновый прогрев всего фильма на диск (:class:`Vault`).

    Порядок работы: сначала вперёд от места, откуда начали смотреть, — это то, что
    понадобится раньше всего, — потом голова фильма, если начали с середины. Внутри
    каждого куска работы это ОДИН прогон ffmpeg от края до края (см. заголовок модуля).
    """

    source: str
    audio: int
    grid: Grid
    vault: Vault
    #: Чем кодировать видео (:class:`torrcast.recode.Encode`); ``None`` - копия.
    encode: Any = None
    #: С какого места смотрим: прогрев идёт отсюда вперёд, голова - потом.
    began_at: int = 0
    rate: float = WARM_RATE
    nice: int = WARM_NICE
    log: Any = None
    #: Запас живого показа, секунды; кладёт :func:`torrcast.cli._hold` на каждом опросе.
    slack: float = 0.0
    #: Прогрев замер под просевшим запасом (:data:`GUARD_LOW`).
    idle: bool = False
    #: С какого момента (монотонные секунды) запас держится над :data:`GUARD_LOW`, пока
    #: прогрев замер; ``0.0`` - ещё не поднялся или прогрев не замирал. По этой выдержке
    #: тесный, но здоровый показ оживляет прогрев, не дожидаясь :data:`GUARD_HIGH`
    #: (:meth:`_may_resume`).
    healthy_since: float = 0.0
    #: Почему прогрев дальше не идёт: бюджет диска, мёртвый источник. Пусто - идёт.
    trouble: str = ""
    stopped: bool = False
    thread: Any = None
    packer: Any = None
    lock: Any = field(default_factory=threading.Lock)
    #: Сколько прогонов оборвалось само (сеть). Считается ради честной строки, не ради лимита.
    breaks: int = 0
    #: Чем продолжить, когда эта серия ляжет на диск целиком: фабрика прогрева следующей
    #: серии (``() -> Warmer | None``) или ``None`` - продолжать нечем.
    #:
    #: Фабрика, а не готовый прогрев: следующей серии нужны и паспорт, и карта опорных
    #: кадров, а это запросы к рою, которые не имеют права идти, пока грузится текущая.
    #: Зовётся ровно один раз и ровно тогда, когда текущая серия уже не нуждается в сети.
    follow: Any = None
    #: Прогрев следующей серии, поднятый :meth:`_chain`; ``None`` - ещё не поднимали.
    after: Warmer | None = None

    def start(self) -> None:
        self.vault.open()
        self.thread = threading.Thread(target=self._work, daemon=True, name="torrcast-warm")
        self.thread.start()

    def stop(self) -> None:
        """Снять прогрев. Прогретое **не трогаем**: показ может продолжиться завтра."""
        self.stopped = True
        with self.lock:
            packer, self.packer = self.packer, None
        if packer is not None:
            packer.stop(keep_files=True, reason="показ окончен")
        if self.after is not None:
            self.after.stop()

    def feed(self, slack: float) -> None:
        """Запас живого показа - прогреву и его продолжению (:meth:`_throttle`).

        Число одно на всю цепочку: и прогрев этой серии, и прогрев следующей тянут из той
        же раздачи и жгут тот же процессор, поэтому проседание показа обязано ронять оба.
        """
        self.slack = slack
        if self.after is not None:
            self.after.feed(slack)

    @property
    def warmed(self) -> float:
        """Сколько секунд фильма уже лежит на диске."""
        return sum(self.grid.span(slot) for slot in self.vault.slots())

    @property
    def done(self) -> bool:
        """Весь фильм на диске: показ дальше не нуждается в сети вовсе."""
        return len(self.vault.slots()) >= self.grid.count

    def line(self) -> str:
        """Строка о прогреве для журнала и статуса — та самая «прогрето 42 мин из 96»."""
        from torrcast.cli import _hms

        head = f"прогрето {_hms(self.warmed)} из {_hms(self.grid.duration)}"
        if self.done:
            done = f"{head} - фильм целиком на диске, интернет больше не нужен"
            return done if self.after is None else f"{done}; следующая: {self.after.line()}"
        if self.trouble:
            return f"{head} - прогрев встал: {self.trouble}"
        return f"{head} - грею дальше" + (" (жду запаса показа)" if self.idle else "")

    def _missing(self) -> tuple[int, int] | None:
        """Куда идти прогреву: ``(первый непрогретый, последний слот прогона)``.

        Сначала хвост от места показа, потом голова: обрыв связи бьёт по будущему, а не
        по уже пройденному. Прогон всегда доводится до конца своего участка — это и есть
        «один прогон, один непрерывный звук».
        """
        have = self.vault.slots()
        for first in range(self.began_at, self.grid.count):
            if first not in have:
                return first, self.grid.count - 1
        for first in range(0, self.began_at):
            if first not in have:
                return first, self.began_at - 1
        return None

    def _wait_for_picture(self) -> None:
        """Дождаться, пока у показа появится запас, и только потом лезть в раздачу.

        ⚠️ Замер: прогрев, поднятый вместе с показом, отнимает у первого сегмента 0.2 с
        (2.10 → 2.28 с готовности LOAD на «Моане 2») — свой ffmpeg, свой запрос к той же
        раздаче. Путь до картинки дорожать не имеет права ни на сотую, поэтому прогрев
        стоит, пока живая упаковка не наберёт запас, и трогается с места уже при играющем
        показе. Потолок ожидания нужен на случай, когда запас не меряют вовсе (mock,
        приёмник молчит): тогда прогрев всё равно начнётся, просто позже.
        """
        deadline = time.monotonic() + START_GRACE
        while not self.stopped and self.slack < GUARD_HIGH and time.monotonic() < deadline:
            time.sleep(0.5)

    def _work(self) -> None:
        self._wait_for_picture()
        while not self.stopped:
            try:
                job = self._missing()
                if job is None:
                    if not self.trouble:
                        self._say(self.line())
                        mark("прогрев готов", секунд=round(self.warmed))
                        self._chain()
                    return
                tight = self.vault.fit(int(self._forecast(*job)))
                if tight:
                    self._stall(tight)
                    return
                self._run(*job)
            except Exception as exc:  # прогрев не имеет права ронять показ
                self._say(f"прогрев сорвался ({exc}) - показ идёт как обычно")
                time.sleep(5.0)

    def _chain(self) -> None:
        """Серия легла на диск целиком - взяться за следующую (:attr:`follow`).

        Ровно за одну, и ни серией дальше. Причина не в бюджете, а в том, ради чего
        прогрев вообще есть: обрыв связи убивает показ на **стыке** серий - досмотрели
        текущую, а следующей нет ни куска, и автопереход упирается в мёртвую раздачу.
        Закрывает эту дыру одна серия вперёд; сезон-пак впрок - это уже не страховка
        показа, а выкачивание раздачи на диск, чего мы не делаем нигде.

        Поднимается ровно здесь и ни секундой раньше: пока текущая серия не на диске,
        каждый байт раздачи нужен ей, а не следующей.
        """
        if self.stopped or self.follow is None or self.after is not None or not self.done:
            return
        try:
            following = self.follow()
        except Exception as exc:  # прогрев не имеет права ронять показ
            self._say(f"прогрев следующей серии не собрался ({exc}) - показ идёт как обычно")
            return
        if following is None:
            return
        # Текущая серия для соседнего прогрева - чужой каталог, и бюджет вытеснил бы её
        # первой: она и старше, и досматривать её ещё полчаса (:attr:`Vault.keep`).
        following.vault.keep = following.vault.keep | {self.vault.key}
        self.after = following
        following.slack = self.slack
        following.start()
        mark("прогрев следующей серии")

    def _forecast(self, first: int, last: int) -> float:
        """Во сколько байт обойдётся этот участок. Считаем по нашему же битрейту, когда
        перекодируем, и по уже прогретому (или по потолку), когда копируем."""
        from torrcast.stream import AUDIO_MBIT, MAX_SEGMENT_BYTES, TS_OVERHEAD

        seconds = sum(self.grid.span(s) for s in range(first, last + 1))
        if self.encode is not None:
            mbit = float(self.encode.mbit)
            return (mbit + AUDIO_MBIT) * TS_OVERHEAD * seconds * 1e6 / 8
        # Копия: вес куска задан сеткой, и она сама зажата потолком сегмента.
        return seconds / max(self.grid.span(first), 1.0) * MAX_SEGMENT_BYTES

    def _stall(self, why: str) -> None:
        self.trouble = why
        self._say(self.line())
        mark("прогрев встал", причина=why, секунд=round(self.warmed))

    def _run(self, first: int, last: int) -> None:
        """Один прогон ffmpeg: от ``first`` до ``last`` включительно, на диск, в темпе."""
        from torrcast.stream import Packer, ffmpeg_pack_command

        command = ffmpeg_pack_command(
            self.source,
            self.audio,
            str(self.vault.dir / RUN_DIR),
            self.grid,
            first,
            self.grid.start(first),
            readrate=self.rate,
            burst=0.0,
            encode=self.encode,
            until=last,
        )
        command = ["nice", "-n", str(self.nice), *command]
        began = time.monotonic()
        mark("прогрев пошёл", первый=first, последний=last, темп=self.rate)
        self._say(f"грею на диск с {self.grid.start(first) / 60:.0f}-й минуты, темп ×{self.rate:g}")
        with self.lock:
            self.packer = packer = Packer.start(
                command, self.vault.dir, self.vault.dir / RUN_DIR, first, last=last
            )
        try:
            while not self.stopped:
                packer.publish()
                if packer.edge >= last or packer.poll() is not None:
                    break
                self._throttle(packer)
                time.sleep(0.5)
        finally:
            self._resume(packer)
            with self.lock:
                self.packer = None
            packer.stop(keep_files=True, reason="прогрев окончен")
            self.vault.touch()
        got = max(0, min(last, packer.edge) - first + 1)
        spent = time.monotonic() - began
        if got and packer.poll() not in (0, None) and packer.edge < last:
            # Прогон оборвался сам - почти всегда это пропавшая сеть. Не авария:
            # следующий круг начнёт с первого непрогретого куска, когда сеть вернётся.
            self.breaks += 1
            self._say(f"прогрев оборвался на {self.grid.end(packer.edge) / 60:.0f}-й минуте")
            time.sleep(5.0)
        elif not got:
            self._say(f"прогрев не дал ни куска за {spent:.0f} с - жду и пробую снова")
            time.sleep(10.0)

    def _throttle(self, packer: Any) -> None:
        """Запас показа просел — прогрев замирает; вырос (или долго здоров) — оживает.

        Именно ``SIGSTOP``, а не «снять и начать заново»: снятый прогон обошёлся бы
        показу дырой в звуке на стыке (заголовок модуля), а замерший продолжает с того
        же кадра. Живой упаковке это не грозит ничем: замирает читатель диска, а не тот
        ffmpeg, чьи куски забирает приёмник.
        """
        if self.slack <= 0:  # запаса ещё не мерили - не мешаем показу гадать за нас
            return
        if not self.idle and self.slack < GUARD_LOW:
            self.idle = True
            self.healthy_since = 0.0
            with contextlib.suppress(OSError, ProcessLookupError):
                packer.proc.send_signal(signal.SIGSTOP)
            mark("прогрев замер", запас=round(self.slack))
        elif self.idle and self._may_resume():
            self._resume(packer)

    def _may_resume(self) -> bool:
        """Пора ли оживлять замерший прогрев.

        Два повода, и оба безопасны для показа. Первый - запас перевалил :data:`GUARD_HIGH`:
        показ с большим отрывом от края, места хватает обоим. Второй - запас держится над
        :data:`GUARD_LOW` дольше :data:`STARVE_GRACE`: это тесный, но здоровый показ (идёт
        вплотную за упаковкой, до :data:`GUARD_HIGH` не дотягивает никогда), и без короткого
        захода прогрев голодал бы вечно. Стоит запасу просесть ниже :data:`GUARD_LOW` -
        выдержка обнуляется, и прогрев остаётся замершим: живой показ всегда важнее.
        """
        if self.slack > GUARD_HIGH:
            return True
        if self.slack < GUARD_LOW:
            self.healthy_since = 0.0
            return False
        now = time.monotonic()
        if self.healthy_since == 0.0:
            self.healthy_since = now
            return False
        return now - self.healthy_since >= STARVE_GRACE

    def _resume(self, packer: Any) -> None:
        if not self.idle:
            return
        self.idle = False
        self.healthy_since = 0.0
        with contextlib.suppress(OSError, ProcessLookupError):
            packer.proc.send_signal(signal.SIGCONT)

    def _say(self, text: str) -> None:
        if self.log is not None:
            self.log(text)
