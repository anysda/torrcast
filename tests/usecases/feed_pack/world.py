"""Стенд ленты показа: ручные часы, поддельный процесс и мелкий инвентарь.

Часы тут ручные, сна нет вовсе, ffmpeg не поднимается: зеркала обязаны мерить решение
показа, а не терпеливость машины.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from torrcast.adapters.filesystem.remove_tree import remove_tree
from torrcast.adapters.recode.recode_dir import RECODE_DIR
from torrcast.adapters.side_thread import side_thread
from torrcast.adapters.stream_pack._segment_files import _paths
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.forget_playing import forget_playing
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.pack_start import pack_start
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.adapters.stream_probe.segment_slot import segment_slot
from torrcast.usecases.feed_pack.configure import configure
from torrcast.usecases.feed_pack.feed import Feed


@dataclass
class FakeClock:
    """Монотонные часы под рукой зеркала: сон не спит, а двигает стрелку."""

    now: float = 1000.0
    slept: list[float] = field(default_factory=list)
    naps: int = 1000

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        if len(self.slept) > self.naps:
            raise AssertionError(
                f"показ уснул {len(self.slept)} раз подряд: ожидание не кончается. "
                "Самое долгое честное ожидание тут - `wait` по 0.2 с, то есть сотни "
                "снов, так что тысяча - это уже вечный цикл."
            )


@dataclass
class FakeProc:
    """Процесс упаковки, которым распоряжается зеркало, а не операционная система."""

    code: int | None = None
    signals: list[str] = field(default_factory=list)

    def poll(self) -> int | None:
        return self.code

    def wait(self, timeout: float | None = None) -> int:
        self.code = 0 if self.code is None else self.code
        return self.code

    def terminate(self) -> None:
        self.signals.append("terminate")
        if self.code is None:
            self.code = -15

    def kill(self) -> None:
        self.signals.append("kill")
        self.code = -9

    def send_signal(self, number: int) -> None:
        self.signals.append(f"signal {number}")


@dataclass
class FakeVault:
    """Хранилище прогретого: каталог на диске под именами той же сетки."""

    dir: Path

    def path(self, slot: int) -> Path:
        return self.dir / f"v{slot}.ts"


def hand(now: float = 1000.0) -> FakeClock:
    """Ручные часы: сна тут нет вовсе, стрелку двигает сам ``sleep``.

    Часов у показа два места: лента держит их слотом композиции (:func:`tract`), а прогон
    упаковки - своим полем (``packer(..., now=hand.monotonic)``). Заведи одно - и зеркало
    мерило бы получасы, где решение ленты идёт по ручной стрелке, а замер прогона по
    настоящей.
    """
    return FakeClock(now=now)


def tract(**parts: Any) -> FakeClock:
    """Собрать ленте её внешний мир - тот же, что и боевой корень, кроме названного.

    Слоты перечислены здесь поимённо и ровно теми же, что заполняет
    :func:`torrcast.runtime.wire_feed.wire_feed`: промах виден глазами, а перенос единицы
    между файлами ломает стенд там же, где ломает боевую проводку, - на импорте, а не
    молча посреди зелёного прогона.

    Возвращает ручные часы стенда: сна тут нет вовсе, а стрелку двигает сам ``sleep``.
    Боевую проводку возвращает фикстура ``_rewired`` этого пакета - после каждой пробы.
    """
    ticking = cast(FakeClock, parts.pop("clock", None) or hand(parts.pop("now", 1000.0)))
    configure(
        parts.pop("segment_name", segment_name),
        parts.pop("segment_slot", segment_slot),
        parts.pop("pack_start", pack_start),
        parts.pop("pack_command", ffmpeg_pack_command),
        parts.pop("packer", Packer),
        parts.pop("forget_flag", forget_playing),
        parts.pop("recode_dir", RECODE_DIR),
        parts.pop("remove_tree", remove_tree),
        parts.pop("segment_paths", _paths),
        ticking,
        parts.pop("spawn", side_thread),
    )
    assert not parts, f"стенд не знает таких слотов: {sorted(parts)}"
    return ticking


def here(work: Any) -> None:
    """Подъём в стороне - прямо здесь: зеркалу нужен порядок, а не второй поток.

    Слот этот боевой поднимает демона (:func:`torrcast.adapters.side_thread.side_thread`),
    и с ним проба мерила бы гонку двух потоков вместо решения показа. Что работа и правда
    идёт в стороне, меряется отдельно и с настоящим потоком.
    """
    work()


def factory(start: Any) -> Any:
    """Завод прогона упаковки из одной ручки ``start`` - в объёме порта, и не больше."""
    return type("StandPacker", (), {"start": staticmethod(start)})


def grid(duration: float = 60.0, step: float = 10.0) -> Grid:
    """Ровная сетка: шесть кусков по десять секунд."""
    return Grid.uniform(duration, step)


def packer(root: Path, **kwargs: Any) -> Packer:
    """Прогон упаковки поверх свежих каталогов, без единого ffmpeg.

    Часы прогону называет тот, кому они важны: ``packer(..., now=hand.monotonic)``.
    ``kind`` - каким классом собрать прогон: зеркалу иногда нужен наследник, у которого
    одна ступень подменена своей (так меряется замок выкладки, не трогая саму выкладку).
    """
    kind = kwargs.pop("kind", None) or Packer
    out = kwargs.pop("out", None) or root / "out"
    run = kwargs.pop("run", None) or out / "pack"
    out.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    proc = kwargs.pop("proc", None) or FakeProc()
    built: Packer = kind(proc=proc, out=out, run=run, **kwargs)
    return built


def feed(root: Path, **kwargs: Any) -> Feed:
    """Лента показа на ровной сетке поверх свежего каталога показа."""
    out = kwargs.pop("out", None) or root / "out"
    out.mkdir(parents=True, exist_ok=True)
    lines = kwargs.pop("grid", None) or grid()
    kwargs.setdefault("wait", 0.0)
    return Feed(source="src", audio=0, out=out, grid=lines, **kwargs)


def signals(run: Packer) -> list[str]:
    """Какие сигналы получил процесс прогона: на стенде он поддельный и это знает стенд."""
    return cast(FakeProc, run.proc).signals


def vault(root: Path) -> FakeVault:
    """Каталог прогретого на диске."""
    where = root / "warm"
    where.mkdir(parents=True, exist_ok=True)
    return FakeVault(dir=where)


def lay(where: Path, slot: int, size: int = 1024) -> Path:
    """Положить в каталог кусок нужного веса под именем сетки."""
    path = where / f"v{slot}.ts"
    path.write_bytes(b"x" * size)
    return path
