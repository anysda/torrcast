"""Поддельная среда прогрева и мелкий инвентарь: общее для зеркал пакета прогрева.

Часы тут ручные, сна нет вовсе, а телеметрия складывается в списки: зеркала обязаны
мерить решение прогрева, а не терпеливость машины.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.warm_environment import environment
from torrcast.usecases.warm.configure import configure
from torrcast.usecases.warm.vault import Vault
from torrcast.usecases.warm.warmer import Warmer
from torrcast.usecases.warm.warmer_state import _State


@dataclass
class FakeEnvironment:
    """Часы, диск и телеметрия прогрева под наблюдением зеркала."""

    now: float = 1000.0
    slept: list[float] = field(default_factory=list)
    marks: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    events: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)
    stamp: float = 1_700_000_000.0
    naps: int = 1000
    #: Медиатракт прогрева. Умолчания тут БОЕВЫЕ и названы теми же именами, что в корне
    #: (:data:`torrcast.adapters.warm_environment.environment`): зеркало подменяет ровно ту
    #: ступень, которую меряет, а остальные остаются настоящими.
    packer: Any = environment.packer_type
    pack: Any = environment.pack_command
    pilot: Any = environment.pack_start
    names: Any = environment.segment_name
    slots: Any = environment.segment_slot
    clock_face: Any = environment.hms
    audio_mbit: float = environment.audio_mbit
    max_segment_bytes: int = environment.max_segment_bytes
    ts_overhead: float = environment.ts_overhead

    def epoch(self) -> float:
        return self.stamp

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        if len(self.slept) > self.naps:
            raise AssertionError(
                f"прогрев уснул {len(self.slept)} раз подряд: ожидание не кончается. "
                "Самое долгое честное ожидание тут - START_GRACE по полсекунды, "
                "то есть под сотню снов, так что тысяча - это уже вечный цикл."
            )

    def remove_tree(self, path: object) -> None:
        import shutil

        where = Path(str(path))
        self.removed.append(where)
        shutil.rmtree(where, ignore_errors=True)

    def emit(self, event: str, *args: object, **facts: object) -> None:
        self.events.append((event, args, dict(facts)))

    def mark(self, name: str, **facts: object) -> None:
        self.marks.append((name, dict(facts)))

    def segment_name(self, slot: int) -> str:
        return str(self.names(slot))

    def segment_slot(self, name: str) -> int:
        return int(self.slots(name))

    def hms(self, seconds: float) -> str:
        return str(self.clock_face(seconds))

    @property
    def packer_type(self) -> Any:
        return self.packer

    def pack_command(self, *args: Any, **kwargs: Any) -> Any:
        return self.pack(*args, **kwargs)

    def pack_start(self, source_url: str, at: float) -> Any:
        return self.pilot(source_url, at)

    def named(self, name: str) -> dict[str, Any]:
        """Поля метки с таким именем; нет метки - пустой словарь."""
        for mark, facts in self.marks:
            if mark == name:
                return facts
        return {}


class LiveTract:
    """Боевая среда прогрева, у которой стенд назвал только медиатракт.

    Часы, диск и телеметрия тут настоящие: сквозные пробы читают ленту следа и ждут
    живого ffmpeg, и подделка среды доказывала бы там собственную тишину. Подменяется
    ровно то, что поднимает второй процесс: завод захода и пробный прогон.
    """

    def __init__(self, packer: Any = None, pilot: Any = None) -> None:
        self._packer = packer if packer is not None else environment.packer_type
        self._pilot = pilot if pilot is not None else environment.pack_start

    def __getattr__(self, name: str) -> Any:
        return getattr(environment, name)

    @property
    def packer_type(self) -> Any:
        return self._packer

    def pack_start(self, source_url: str, at: float) -> float:
        return float(self._pilot(source_url, at))


def live_tract(**parts: Any) -> LiveTract:
    """Подключить прогреву боевую среду, назвав стендом только её медиатракт."""
    tract = LiveTract(**parts)
    configure(tract)
    return tract


def world(kind: Any = None, **parts: Any) -> FakeEnvironment:
    """Собрать прогреву его внешний мир: тот же корень, что и боевой, кроме названного.

    Одним вызовом :func:`torrcast.usecases.warm.configure`, ровно как это делает боевая
    проводка: слоты заполняет среда целиком, и половинчатая замена невозможна по
    устройству. Боевую среду возвращает фикстура ``_rewired`` этого пакета - после
    каждой пробы.
    """
    fake: FakeEnvironment = (kind or FakeEnvironment)(**parts)
    configure(fake)
    return fake


#: Сколько ждать нитку прогрева после снятия. Нитка узнаёт о снятии на ближайшем круге,
#: то есть за миллисекунды; потолок стоит ради того, чтобы не подвесить прогон навсегда.
QUIET = 5.0


def quiet(warm: _State) -> None:
    """Снять прогрев и ДОЖДАТЬСЯ его нитки - вместе с ниткой следующей серии.

    :meth:`stop` только ставит флаг: нитка узнаёт о снятии на ближайшем круге, а до того
    успевает и поспать, и поднять ffprobe - уже в среде СОСЕДНЕЙ пробы, потому что среду
    прогрева она читает в момент вызова (:mod:`torrcast.usecases.warm._state`). Дожидается
    нитку та проба, которая её и подняла: иначе покраснеет сосед.
    """
    warm.stop()
    end = time.monotonic() + QUIET
    chain: _State | None = warm
    while chain is not None:
        thread = chain.thread
        if thread is not None:
            thread.join(timeout=max(0.0, end - time.monotonic()))
        chain = chain.after


def grid(duration: float = 60.0, step: float = 10.0) -> Grid:
    """Ровная сетка: шесть кусков по десять секунд."""
    return Grid.uniform(duration, step)


def vault(root: Path, key: str = "k", budget: int = 1 << 30, floor: int = 0) -> Vault:
    """Каталог прогретого с заведомо просторным бюджетом и без запаса раздела."""
    store = Vault(root=root / "warm", key=key, budget=budget, floor=floor)
    store.dir.mkdir(parents=True, exist_ok=True)
    return store


def lay(store: Vault, slot: int, size: int = 1024) -> Path:
    """Положить в каталог прогретого кусок нужного веса."""
    path = store.path(slot)
    path.write_bytes(b"x" * size)
    return path


def warmer(root: Path, **kwargs: Any) -> Warmer:
    """Прогрев на ровной сетке поверх свежего каталога.

    ``kind`` - каким классом собрать прогрев: зеркалу нитки нужен наследник, у которого
    заход считает решения вместо того, чтобы поднимать ffmpeg (:func:`counting`).
    """
    kind = kwargs.pop("kind", None) or Warmer
    lines = kwargs.pop("grid", None) or grid()
    store = kwargs.pop("vault", None) or vault(root)
    built: Warmer = kind(source="src", audio=0, grid=lines, vault=store, **kwargs)
    return built


def follower(root: Path, **kwargs: Any) -> Warmer:
    """Прогрев следующей серии для проб цепочки: нитку поднимает, а работы не берёт.

    Проба цепочки меряет, ВЗЯЛИ ли следующую серию в работу; как она греется - предмет
    других проб, и поднимать ради этого настоящий ffprobe незачем. ``trouble`` кончает
    нитку на первом же круге и не трогает ``stopped``: по нему проверяется снятие показа.
    """
    made = warmer(root, **kwargs)
    made.trouble = "проба цепочки: этому прогреву работы не дано"
    return made


def counting() -> tuple[Any, list[tuple[int, int, bool]]]:
    """Прогрев, у которого заход только записан, и список того, что он взял в работу.

    Нитка прогрева проверяется по РЕШЕНИЯМ - порядку участков и остановкам, - а не по
    тому, поднялся ли ffmpeg. Заход тут - единственная ступень, которую зеркало отводит
    в сторону, и отводит наследованием: подпись остаётся под присмотром тайпчека.
    """
    taken: list[tuple[int, int, bool]] = []

    class Counted(Warmer):
        def _run(self, first: int, last: int, spot: bool = False) -> None:
            taken.append((first, last, spot))
            self.stopped = True

    return Counted, taken


def falling(boom: Exception) -> Any:
    """Прогрев, у которого заход срывается: своя беда - это строка и пауза, не смерть показа."""

    class Falls(Warmer):
        def _run(self, first: int, last: int, spot: bool = False) -> None:
            self.stopped = True
            raise boom

    return Falls
