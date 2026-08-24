"""Один заход прогрева: пробный прогон, вежливый ``nice``, сверка укладки и честный итог."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from tests.usecases.warm.world import grid, warmer, world
from torrcast.adapters.recode.encode import Encode
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS
from torrcast.usecases.warm.run import _run
from torrcast.usecases.warm.settings import RUN_DIR
from torrcast.usecases.warm.vault import Vault

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class _Encode:
    mbit: float = 8.0

    def fit(self, span: float, cap: float, cap_mbit: float = 0.0) -> _Encode:
        """Ужатие под кусок стендом: цель кладётся ровно в потолок веса этой длины."""
        return replace(self, mbit=min(self.mbit, cap * 8 / span / 1e6))


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
    cap: int = 0
    shrink: Any = None
    code: int | None = None
    stopped: list[str] = field(default_factory=list)
    proc: _Process = field(default_factory=_Process)

    def publish(self) -> None:
        if self.edge < self.last:
            self.edge += 1
            # Выкладка продукта - ПЕРЕИМЕНОВАНИЕ из каталога прогона, а не запись поверх
            # готового имени: под этим именем может лежать копия, которую придерживает
            # точечный перекод, и запись поверх поменяла бы её прямо под ним.
            piece = self.run / f"v{self.edge}.ts"
            piece.write_bytes(b"x")
            os.replace(piece, self.out / f"v{self.edge}.ts")

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
        packer = _Packer(
            out=out,
            run=run,
            first=first,
            last=kwargs["last"],
            edge=first - 1,
            cap=kwargs.get("cap", 0),
        )
        packer.shrink = kwargs.get("shrink")
        packers.append(packer)
        return packer

    parts = {
        "pilot": lambda source, at: (at, at - 2.0),
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


def test_a_running_copy_reserves_one_next_piece_at_a_time(tmp_path: Path, monkeypatch: Any) -> None:
    """По ходу длинного захода остаток фильма не заявляется местом заранее."""
    packers: list[_Packer] = []
    parts, _ = _tract(packers)
    world(**parts)
    warm = warmer(tmp_path, log=[].append)
    asked: list[int] = []

    def fit(_vault: Vault, need: int) -> str:
        asked.append(need)
        return ""

    monkeypatch.setattr(Vault, "fit", fit)

    _run(warm, 0, 2)

    assert asked
    assert max(asked) == int(warm._forecast(1, 1))


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


def test_a_spot_run_lays_its_picture_with_the_sound_of_the_copy(tmp_path: Path) -> None:
    """🔴 Точечный перекод стирает копию, а её звук нужен склейке: копия придерживается ссылкой.

    Без этого на диске остаётся перекод со СВОЕЙ сеткой AAC, и стык с соседями рвётся на
    47.3-54.7 мс - замер на уложенном каталоге двухчасовой картины.
    """
    seen: list[tuple[int, str, bytes, int]] = []

    def lay_spot(slot: int, laid: Path, copy: Path, cap: int) -> bool:
        seen.append((slot, laid.name, copy.read_bytes(), cap))
        return True

    packers: list[_Packer] = []
    parts, _ = _tract(packers)
    world(lay_spot=lay_spot, **parts)
    warm = warmer(tmp_path, spot_encode=_Encode(), log=[].append)
    warm.vault.path(4).write_bytes("копия этого места".encode())

    _run(warm, 4, 4, spot=True)

    assert seen == [(4, "v4.ts", "копия этого места".encode(), warm.cap)], (
        "звук копии не доехал до выкладки точечного перекода"
    )
    assert not (warm.vault.dir / "a4.ts").exists(), "ссылка на копию осталась лежать"


def test_a_run_that_is_not_pointwise_lays_nothing_over_a_copy(tmp_path: Path) -> None:
    """Сплошной заход кладёт своё и ничего не склеивает: копии под ним нет и быть не должно."""
    called: list[int] = []

    def lay_spot(slot: int, *args: Any, **kwargs: Any) -> bool:
        called.append(slot)
        return True

    packers: list[_Packer] = []
    parts, _ = _tract(packers)
    world(lay_spot=lay_spot, **parts)
    warm = warmer(tmp_path, log=[].append)

    _run(warm, 2, 3)

    assert called == [], "сплошной заход полез в выкладку точечного перекода"


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


def test_a_run_weighs_its_pieces_by_the_ceiling_of_the_receiver_it_warms_for(
    tmp_path: Path,
) -> None:
    """Заход зажимает вес куска потолком ТОГО приёмника, для которого греет.

    Умолчание завода упаковщика - осторожный профиль
    (:attr:`torrcast.domain.profile.CAUTIOUS.max_segment_bytes`), и не сказать ему потолок
    значит сказать 16 МБ. У приёмника с потолком выше весь класс кусков между двумя
    потолками считался бы тяжёлым и уходил бы на диск обходным путём
    (:func:`torrcast.usecases.warm.lay_heavy._lay_heavy`) вместо обычной выкладки.

    Незнакомому приёмнику по-прежнему достаётся осторожный: умолчание тут не трогается,
    оно приезжает из состояния прогрева (:attr:`torrcast.usecases.warm.warmer_state._State.cap`).
    """
    packers: list[_Packer] = []
    parts, _ = _tract(packers)
    world(**parts)
    warm = warmer(tmp_path, cap=ANDROID_TV.max_segment_bytes, log=[].append)

    _run(warm, 0, 1)

    assert ANDROID_TV.max_segment_bytes != CAUTIOUS.max_segment_bytes, "потолки сравнялись"
    assert packers[0].cap == warm.cap, "заход мерил куски чужим потолком"


def test_an_unknown_receiver_still_gets_the_cautious_ceiling(tmp_path: Path) -> None:
    """Отрицательная проба: не названный потолок остаётся осторожным, а не любым."""
    packers: list[_Packer] = []
    parts, _ = _tract(packers)
    world(**parts)
    warm = warmer(tmp_path, log=[].append)

    _run(warm, 0, 1)

    assert packers[0].cap == CAUTIOUS.max_segment_bytes, "умолчание перестало быть осторожным"


def test_a_spot_run_fits_its_target_to_the_length_of_the_piece(tmp_path: Path) -> None:
    """🔴 Цель точечного перекода считается от ДЛИНЫ куска, а не берётся константой.

    Живой замер приставки (потолок куска 28 МБ, цель приёмника 28 Мбит/с): постоянная цель
    положила в кусок 19.972 с 69.64 МБ - тяжелее той самой копии, поверх которой перекод и
    шёл. Склейка в потолок не влезла, место осталось копией на весь сеанс, и показ платил
    за него ожиданием на каждом заходе.
    """
    packers: list[_Packer] = []
    parts, _ = _tract(packers)
    seen: list[Any] = []

    def pack(*args: Any, **kwargs: Any) -> list[str]:
        seen.append(kwargs.get("encode"))
        return ["ffmpeg", "-i"]

    parts["pack"] = pack
    world(**parts)
    warm = warmer(
        tmp_path,
        grid=grid(duration=120.0, step=20.0),
        spot_encode=Encode(preset="ultrafast", mbit=ANDROID_TV.recode_mbit),
        cap=ANDROID_TV.max_segment_bytes,
        threshold=ANDROID_TV.recode_at_mbit,
        log=[].append,
    )

    _run(warm, 4, 4, spot=True)

    span = warm.grid.span(4)
    weight = seen[0].mbit * span * 1e6 / 8
    assert weight <= warm.cap, (
        f"цель {seen[0].mbit:.2f} Мбит/с кладёт в кусок {span:.3f} с "
        f"{weight / 1e6:.2f} МБ при потолке {warm.cap / 1e6:g} МБ"
    )
