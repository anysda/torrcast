"""Один заход прогрева: пробный прогон, вежливый ``nice``, сверка укладки и честный итог."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from tests.usecases.warm.world import warmer, world
from torrcast.usecases.warm.run import _run
from torrcast.usecases.warm.settings import RUN_DIR

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class _Encode:
    mbit: float = 8.0


@dataclass
class _Process:
    signals: list[int] = field(default_factory=list)


@dataclass
class _Packer:
    """Упаковщик, который выкладывает по куску на каждый ``publish``."""

    out: Any = None
    run: Any = None
    first: int = 0
    last: int = -1
    edge: int = -1
    shrink: Any = None
    code: int | None = None
    stopped: list[str] = field(default_factory=list)
    proc: _Process = field(default_factory=_Process)

    def publish(self) -> None:
        if self.edge < self.last:
            self.edge += 1
            (self.out / f"v{self.edge}.ts").write_bytes(b"x")

    def poll(self) -> int | None:
        return self.code if self.edge >= self.last else None

    def stop(self, keep_files: bool = False, reason: str = "") -> None:
        self.stopped.append(reason)


def _tract(packers: list[_Packer]) -> tuple[dict[str, Any], list[list[str]]]:
    """Медиатракт захода стендом; возвращает слоты для :func:`world` и команды ffmpeg."""
    commands: list[list[str]] = []

    def _start(command: list[str], out: Any, run: Any, first: int, **kwargs: Any) -> _Packer:
        commands.append(command)
        run.mkdir(parents=True, exist_ok=True)
        packer = _Packer(out=out, run=run, first=first, last=kwargs["last"], edge=first - 1, **{})
        packer.shrink = kwargs.get("shrink")
        packers.append(packer)
        return packer

    parts = {
        "pilot": lambda source, at: at - 2.0,
        "pack": lambda *args, **kwargs: ["ffmpeg", "-i"],
        "packer": type("StandPacker", (), {"start": staticmethod(_start)}),
    }
    return parts, commands


def test_a_copy_run_asks_the_pilot_and_goes_nice(tmp_path: Path) -> None:
    """Копия заходит от ИЗМЕРЕННОГО начала и всегда под ``nice``: резы считаются от него."""
    packers: list[_Packer] = []
    parts, commands = _tract(packers)
    fake = world(**parts)
    warm = warmer(tmp_path, log=[].append)

    _run(warm, 2, 3)

    assert commands == [["nice", "-n", str(warm.nice), "ffmpeg", "-i"]]
    assert fake.named("пробный прогон прогрева") == {"слот": 2, "встали": 18.0}
    assert fake.named("прогрев пошёл")["режим"] == "копия"
    assert warm.vault.slots() == {2, 3}, "заход не выложил свой участок"
    assert packers[0].stopped == ["прогрев окончен"]


def test_a_recoding_run_needs_no_pilot(tmp_path: Path) -> None:
    """У перекодирующего захода ``-ss`` точен: пробный увёл бы весь заход на сегмент назад."""
    packers: list[_Packer] = []
    parts, _ = _tract(packers)
    fake = world(**parts)
    warm = warmer(tmp_path, encode=_Encode(), log=[].append)

    _run(warm, 0, 1)

    assert fake.named("пробный прогон прогрева") == {}, "перекод сходил за пробным прогоном"
    assert fake.named("прогрев пошёл")["режим"] == "перекод"


def test_a_spot_run_marks_the_place_only_after_it_is_laid(tmp_path: Path) -> None:
    """Метка ставится ПОСЛЕ выкладки: оборвался прогон - на месте куска осталась копия."""
    packers: list[_Packer] = []
    parts, _ = _tract(packers)
    world(**parts)
    warm = warmer(tmp_path, spot_encode=_Encode(), log=[].append)

    _run(warm, 4, 4, spot=True)

    assert warm.vault.spot(4).exists(), "точечный перекод лёг, а метки нет"
    assert warm.vault.have(4)


def test_a_piece_off_the_grid_aborts_the_whole_run(tmp_path: Path) -> None:
    """Заход, вставший не туда, кладёт мимо сетки весь участок: доводить его нельзя."""
    packers: list[_Packer] = []
    parts, _ = _tract(packers)
    world(**parts)
    warm = warmer(tmp_path, log=[].append)

    _run(warm, 0, warm.grid.count - 1, began_of=lambda path: 0.0)

    assert warm.misgrid == 1, "промах не оборвал заход"
    # Мера обрыва - счёт промахов, а не то, что осталось лежать. Забракованный кусок
    # сверка стирает сама, поэтому по каталогу оборванный заход неотличим от захода,
    # который домолотил участок до конца и выбросил каждый кусок поодиночке: в обоих
    # случаях в каталоге остаётся один v0. Различает их только след обхода.
    assert warm.skews == {1: 1}, "заход домолотил участок после промаха"
    assert packers[0].edge == 1, "упаковщик продолжал выкладывать после промаха"
    assert warm.vault.slots() == {0}, "кусок мимо сетки остался лежать в показе"


def test_a_run_that_gave_nothing_says_so_and_waits(tmp_path: Path) -> None:
    """Ни куска за заход - это не тишина, а строка и пауза перед новой попыткой."""
    said: list[str] = []
    packers: list[_Packer] = []
    parts, _ = _tract(packers)
    fake = world(**parts)
    warm = warmer(tmp_path, log=said.append)

    _run(warm, 0, -1)

    assert any("не дал ни куска" in line for line in said)
    assert fake.slept[-1] == 10.0, "прогрев тут же полез в раздачу снова"


def test_the_heavy_hook_of_the_warming_is_handed_to_the_packer(tmp_path: Path) -> None:
    """Выкладке прогрева нужен свой хук: без него она встала бы на первом тяжёлом куске."""
    packers: list[_Packer] = []
    parts, _ = _tract(packers)
    world(**parts)
    warm = warmer(tmp_path, log=[].append)

    _run(warm, 0, 0)
    run = warm.vault.dir / RUN_DIR
    (run / "v5.ts").write_bytes(b"heavy")

    assert packers[0].shrink is not None
    assert packers[0].shrink(5, 1_000_000) is False, "прогрев пообещал выкладке ужатие"
    assert warm.vault.have(5), "тяжёлый кусок не лёг на диск"
